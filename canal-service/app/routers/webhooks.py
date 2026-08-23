"""Inbound: webhook por driver → normalização → opt-out por regra → orquestrador.

Padrão de webhook do programa (PRD §9): responder 2xx rápido, idempotência
por (driver, message_id), segredo verificado, replay tolerado. O webhook
nunca vaza erro 500 para o driver — falha interna é logada e respondida
com 200.

Segredo: a URL de webhook carrega `?token=` (gerado em POST /canal/config e
rotacionável ao reconfigurar). Evolution e Z-API não assinam o corpo, então o
token na URL é a autenticação; o driver Meta, quando implementado, soma a
verificação de assinatura X-Hub-Signature-256 (ver drivers/meta.py). Payload
sem token válido é descartado SEM processar — respondendo 200 para não gerar
tempestade de retries com conteúdo forjado.
"""

import hmac
import logging
import uuid

import httpx
from fastapi import APIRouter, BackgroundTasks, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal, sessao_org, sessao_worker
from ..drivers.base import DriverCanal, MensagemInbound
from ..drivers.registry import obter_driver
from ..models import ChannelConfig, ChannelMessage, ChannelOptout
from ..optout import CONFIRMACAO_OPTOUT, e_pedido_de_optout

log = logging.getLogger("canal.inbound")
router = APIRouter(tags=["webhooks"])


def encaminhar_ao_orquestrador(org_id: uuid.UUID, inbound: MensagemInbound) -> None:
    """Entrega o inbound normalizado ao agente (PRD §9.1) — fora do caminho do
    2xx ao driver. Falha aqui não derruba o webhook: fica logada; a mensagem já
    está em channel_messages e o humano vê a conversa mesmo sem agente."""
    cfg = settings()
    try:
        resposta = httpx.post(
            cfg.orquestrador_url,
            json={
                "org_id": str(org_id),
                "telefone": inbound.telefone,
                "texto": inbound.texto,
                "message_id": inbound.message_id,
                "timestamp": inbound.timestamp.isoformat() if inbound.timestamp else None,
            },
            headers={"X-Service-Key": cfg.orquestrador_key},
            timeout=30,
        )
        if resposta.status_code >= 400:
            log.warning(
                "orquestrador respondeu %s para inbound de %s",
                resposta.status_code,
                inbound.telefone,
            )
    except httpx.HTTPError:
        log.exception("orquestrador inacessível — inbound de %s ficou só registrado", inbound.telefone)


def _resolver_config(db: Session, driver: str, instancia: str) -> ChannelConfig | None:
    sessao_worker(db)  # a instância chega no payload; a org sai da config
    return db.scalar(
        select(ChannelConfig).where(
            ChannelConfig.driver == driver,
            ChannelConfig.instancia == instancia,
            ChannelConfig.ativo,
        )
    )


def _processar(driver_obj: DriverCanal, inbound: MensagemInbound, token: str) -> dict:
    with SessionLocal() as db:
        config = _resolver_config(db, driver_obj.nome, inbound.instancia)
        if config is None:
            log.warning(
                "inbound %s de instância desconhecida '%s' — ignorado",
                driver_obj.nome,
                inbound.instancia,
            )
            return {"resultado": "instancia_desconhecida"}

        # Segredo verificado ANTES de qualquer efeito (PRD §9): sem o token da
        # config, o payload é descartado — inbound forjado não abre janela de
        # sessão, não registra opt-out, não entra na conversa.
        if not hmac.compare_digest(config.webhook_token, token):
            log.warning(
                "inbound %s para instância '%s' com token inválido — descartado",
                driver_obj.nome,
                inbound.instancia,
            )
            return {"resultado": "token_invalido"}

        sessao_org(db, config.org_id)
        # Idempotência por (driver, message_id): reentrega não duplica conversa.
        gravado = db.execute(
            pg_insert(ChannelMessage)
            .values(
                org_id=config.org_id,
                direcao="entrada",
                telefone=inbound.telefone,
                tipo="sessao",
                corpo_renderizado=inbound.texto,
                driver=driver_obj.nome,
                driver_message_id=inbound.message_id,
                status="entregue",
            )
            .on_conflict_do_nothing(constraint="inbound_idempotente")
            .returning(ChannelMessage.id)
        ).scalar()
        if gravado is None:
            db.commit()
            return {"resultado": "replay_ignorado"}

        # Opt-out por regra determinística, ANTES de qualquer LLM (RF-10/IA-04).
        if e_pedido_de_optout(inbound.texto):
            db.execute(
                pg_insert(ChannelOptout)
                .values(org_id=config.org_id, telefone=inbound.telefone, origem="palavra_chave")
                .on_conflict_do_nothing()
            )
            db.add(
                ChannelMessage(
                    org_id=config.org_id,
                    direcao="saida",
                    telefone=inbound.telefone,
                    tipo="sessao",  # resposta à mensagem do cliente: sessão aberta
                    corpo_renderizado=CONFIRMACAO_OPTOUT,
                    driver=driver_obj.nome,
                    status="pendente",
                )
            )
            db.commit()
            from .. import crypto

            try:
                credenciais = {**crypto.decifrar(config.credenciais), "instancia": config.instancia}
                driver_obj.enviar_texto(credenciais, inbound.telefone, CONFIRMACAO_OPTOUT)
            except Exception:
                log.exception("falha ao confirmar opt-out — opt-out registrado mesmo assim")
            return {"resultado": "optout_registrado"}

        db.commit()
        log.info("inbound %s de %s registrado (id %s)", driver_obj.nome, inbound.telefone, gravado)
        return {"resultado": "registrado", "message_id": gravado, "org_id": config.org_id}


def _receber(nome_driver: str):
    async def endpoint(request: Request, background: BackgroundTasks) -> dict:
        # O segredo pode vir na URL (Evolution, Z-API) ou no header — é assim
        # que o Telegram devolve o `secret_token` do setWebhook, e header não
        # vaza em log de acesso nem em referrer.
        token = request.headers.get("X-Telegram-Bot-Api-Secret-Token") or request.query_params.get(
            "token", ""
        )
        payload = await request.json()
        driver_obj = obter_driver(nome_driver)
        try:
            inbound = driver_obj.normalizar_inbound(payload)
        except NotImplementedError:
            return {"resultado": "driver_em_extensao"}
        if inbound is None:
            return {"resultado": "evento_ignorado"}
        if not inbound.instancia:
            # Driver que não se identifica no payload: a instância vem da URL,
            # que é única por organização. Continua sendo o token que autentica.
            from dataclasses import replace

            inbound = replace(inbound, instancia=request.query_params.get("instancia", ""))
        try:
            resultado = _processar(driver_obj, inbound, token)
        except Exception:
            # 2xx rápido sempre: o driver reenvia depois e a idempotência segura o replay
            log.exception("falha ao processar inbound %s", nome_driver)
            return {"resultado": "erro_interno_logado"}
        # Registrado → segue ao agente DEPOIS do 2xx ao driver (assíncrono).
        org_id = resultado.pop("org_id", None)
        if resultado["resultado"] == "registrado" and org_id and settings().orquestrador_url:
            resultado["encaminhado"] = True
            background.add_task(encaminhar_ao_orquestrador, org_id, inbound)
        return resultado

    return endpoint


router.add_api_route(
    "/webhooks/canal/evolution", _receber("evolution"), methods=["POST"],
    summary="Inbound Evolution API",
)
router.add_api_route(
    "/webhooks/canal/zapi", _receber("zapi"), methods=["POST"], summary="Inbound Z-API"
)
router.add_api_route(
    "/webhooks/canal/telegram", _receber("telegram"), methods=["POST"],
    summary="Inbound Telegram Bot API",
)
router.add_api_route(
    "/webhooks/canal/meta", _receber("meta"), methods=["POST"],
    summary="Inbound Meta Cloud API (extensão guiada)",
)
