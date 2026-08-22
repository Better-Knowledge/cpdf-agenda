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

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..db import SessionLocal, sessao_org, sessao_worker
from ..drivers.base import DriverCanal, MensagemInbound
from ..drivers.registry import obter_driver
from ..models import ChannelConfig, ChannelMessage, ChannelOptout
from ..optout import CONFIRMACAO_OPTOUT, e_pedido_de_optout

log = logging.getLogger("canal.inbound")
router = APIRouter(tags=["webhooks"])


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
                driver_obj.enviar_texto(
                    crypto.decifrar(config.credenciais), inbound.telefone, CONFIRMACAO_OPTOUT
                )
            except Exception:
                log.exception("falha ao confirmar opt-out — opt-out registrado mesmo assim")
            return {"resultado": "optout_registrado"}

        db.commit()
        # Próxima etapa (PRD §9.1): normalizada → orquestrador/agente (IA-04).
        log.info("inbound %s de %s registrado (id %s)", driver_obj.nome, inbound.telefone, gravado)
        return {"resultado": "registrado", "message_id": gravado}


def _receber(nome_driver: str):
    async def endpoint(request: Request) -> dict:
        token = request.query_params.get("token", "")
        payload = await request.json()
        driver_obj = obter_driver(nome_driver)
        try:
            inbound = driver_obj.normalizar_inbound(payload)
        except NotImplementedError:
            return {"resultado": "driver_em_extensao"}
        if inbound is None:
            return {"resultado": "evento_ignorado"}
        try:
            return _processar(driver_obj, inbound, token)
        except Exception:
            # 2xx rápido sempre: o driver reenvia depois e a idempotência segura o replay
            log.exception("falha ao processar inbound %s", nome_driver)
            return {"resultado": "erro_interno_logado"}

    return endpoint


router.add_api_route(
    "/webhooks/canal/evolution", _receber("evolution"), methods=["POST"],
    summary="Inbound Evolution API",
)
router.add_api_route(
    "/webhooks/canal/zapi", _receber("zapi"), methods=["POST"], summary="Inbound Z-API"
)
router.add_api_route(
    "/webhooks/canal/meta", _receber("meta"), methods=["POST"],
    summary="Inbound Meta Cloud API (extensão guiada)",
)
