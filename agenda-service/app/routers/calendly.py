"""RF-16 — importar agendamentos do Calendly (opcional, one-way).

Para quem já opera no Calendly e está migrando: o que é marcado lá aparece
aqui, ocupa o horário na grade e entra na agenda do dia. A agenda **nunca**
escreve no Calendly — remarcar e cancelar de verdade acontece lá, e o próximo
webhook reflete aqui.

Três cuidados que moldam o arquivo:

- **A assinatura é a autenticação.** O webhook é público; quem diz de qual
  organização é aquele evento é o HMAC conferido contra a chave gravada. Sem
  assinatura válida, 401 e nada acontece.
- **Idempotência por `external_ref`.** O Calendly reenvia o mesmo evento
  quando não recebe 200. O `uri` do convidado é único e vira a chave.
- **Sempre 200 quando a assinatura confere.** Conflito de horário, serviço
  apagado, payload estranho: tudo responde 200 com `importado: false` e o
  motivo. Um 4xx aqui viraria reentrega eterna.
"""

import hashlib
import hmac
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.orm import Session

from .. import booking, crypto
from ..auth import Credencial, credencial_atual, exigir_escopo
from ..contrato import operacao, respostas, respostas_publicas
from ..db import get_db
from ..errors import ApiError, NaoEncontrado
from ..models import Appointment, CalendlyLink, Resource, Service
from ..schemas import CalendlyConfigIn, CalendlyConfigOut, CalendlyRecebidoOut
from ..sessao import SessionLocal, sessao_org, sessao_worker
from ..tempo import agora_utc, utc

log = logging.getLogger("agenda.calendly")

router = APIRouter(tags=["calendly"])

# O Calendly assina `t=<timestamp>,v1=<hmac>` sobre "<timestamp>.<corpo cru>".
TOLERANCIA_RELOGIO = timedelta(minutes=5)


def _webhook_url(request: Request) -> str:
    from ..config import settings

    base = (settings().base_url_publica or str(request.base_url)).rstrip("/")
    return f"{base}/webhooks/calendly"


# ── Configuração (autenticada) ───────────────────────────────────────────────


def _saida(request: Request, link: CalendlyLink) -> CalendlyConfigOut:
    return CalendlyConfigOut(
        service_id=link.service_id,
        resource_id=link.resource_id,
        cria_lembretes=link.cria_lembretes,
        ativo=link.ativo,
        webhook_url=_webhook_url(request),
        created_at=link.created_at,
    )


@router.get(
    "/integracoes/calendly",
    response_model=CalendlyConfigOut | None,
    summary="Configuração da importação do Calendly",
    description=(
        "null quando a integração não está configurada — ela é **opcional**: sem "
        "configurar, nada muda no produto. A chave de assinatura nunca volta."
    ),
    responses=respostas(),
    openapi_extra=operacao("agenda:admin"),
)
def ver(
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> CalendlyConfigOut | None:
    exigir_escopo(cred, "agenda:admin")
    link = db.scalar(select(CalendlyLink).where(CalendlyLink.org_id == cred.org_id))
    return None if link is None else _saida(request, link)


@router.put(
    "/integracoes/calendly",
    response_model=CalendlyConfigOut,
    summary="Configura (ou reconfigura) a importação do Calendly",
    description=(
        "Grave aqui a signing key da assinatura do webhook e cadastre a "
        "`webhook_url` devolvida no Calendly. Todo agendamento importado entra com "
        "o serviço e o recurso informados — o Calendly não conhece o seu catálogo."
    ),
    responses=respostas("NAO_ENCONTRADO"),
    openapi_extra=operacao("agenda:admin"),
)
def configurar(
    dados: CalendlyConfigIn,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> CalendlyConfigOut:
    exigir_escopo(cred, "agenda:admin")
    booking.carregar_servico(db, cred.org_id, dados.service_id)
    recurso = db.scalar(
        select(Resource).where(Resource.id == dados.resource_id, Resource.org_id == cred.org_id)
    )
    if recurso is None:
        raise NaoEncontrado("Recurso", str(dados.resource_id))

    link = db.scalar(select(CalendlyLink).where(CalendlyLink.org_id == cred.org_id))
    if link is None:
        link = CalendlyLink(org_id=cred.org_id, service_id=dados.service_id,
                            resource_id=dados.resource_id, segredo={})
        db.add(link)
    link.service_id = dados.service_id
    link.resource_id = dados.resource_id
    link.cria_lembretes = dados.cria_lembretes
    link.segredo = crypto.cifrar({"chave": dados.chave_assinatura})
    link.ativo = True
    db.commit()
    db.refresh(link)
    return _saida(request, link)


@router.delete(
    "/integracoes/calendly",
    response_model=CalendlyRecebidoOut,
    summary="Desliga a importação do Calendly",
    description=(
        "Os compromissos já importados **permanecem** na agenda: eles ocupam "
        "horários reais e apagá-los criaria buracos que o prestador não pediu."
    ),
    responses=respostas(),
    openapi_extra=operacao("agenda:admin"),
)
def desligar(
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> CalendlyRecebidoOut:
    exigir_escopo(cred, "agenda:admin")
    link = db.scalar(select(CalendlyLink).where(CalendlyLink.org_id == cred.org_id))
    if link is None:
        return CalendlyRecebidoOut(importado=False, motivo="não havia integração configurada")
    link.ativo = False
    link.segredo = {}
    db.commit()
    return CalendlyRecebidoOut(
        importado=False,
        motivo="integração desligada; os compromissos já importados continuam na agenda",
    )


# ── Webhook (público, autenticado pela assinatura) ───────────────────────────


def _confere(assinatura: str, corpo: bytes, chave: str) -> bool:
    """`Calendly-Webhook-Signature: t=<epoch>,v1=<hex>` sobre `<t>.<corpo>`."""
    partes = dict(
        p.split("=", 1) for p in assinatura.split(",") if "=" in p
    )
    t, v1 = partes.get("t"), partes.get("v1")
    if not t or not v1:
        return False
    try:
        emitido = datetime.fromtimestamp(int(t), tz=agora_utc().tzinfo)
    except ValueError:
        return False
    # Sem a janela de tolerância, uma assinatura capturada valeria para sempre.
    if abs(agora_utc() - emitido) > TOLERANCIA_RELOGIO:
        return False
    esperado = hmac.new(chave.encode(), f"{t}.".encode() + corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, v1)


def _org_do_evento(corpo: bytes, assinatura: str) -> CalendlyLink | None:
    """Qual organização assinou este evento?

    O webhook chega sem sessão e sem org: é a assinatura que a revela. Testar
    contra cada integração ativa é O(orgs com Calendly), que num protótipo é
    um punhado — e é o preço de não pôr o org_id numa URL pública, onde ele
    seria um palpite fácil.

    Duas organizações com a **mesma** chave tornam o evento inatribuível.
    Nesse caso ninguém importa: escolher a primeira significaria pôr o
    compromisso de um cliente na agenda de outra empresa.
    """
    with SessionLocal() as db:
        sessao_worker(db)
        achados = []
        for link in db.scalars(select(CalendlyLink).where(CalendlyLink.ativo)):
            try:
                chave = crypto.decifrar(link.segredo)["chave"]
            except Exception:  # noqa: BLE001 — linha sem segredo utilizável
                continue
            if _confere(assinatura, corpo, chave):
                achados.append(link)
        if len(achados) > 1:
            log.error(
                "duas integrações Calendly com a mesma chave de assinatura (%s) — "
                "evento descartado por ser inatribuível",
                ", ".join(str(a.org_id) for a in achados),
            )
            return None
        if achados:
            db.expunge(achados[0])
            return achados[0]
    return None


def _endereco_do_convidado(payload: dict) -> str:
    """O Calendly nem sempre coleta telefone. Sem ele, o endereço do cliente
    vira `calendly:<uuid do convidado>` — mesma convenção do `tg:<chat_id>`
    do Telegram: autodescritivo, impossível de colidir com E.164, e honesto
    sobre o fato de que não temos como mandar WhatsApp para essa pessoa."""
    from .. import enderecos

    telefone = (payload.get("text_reminder_number") or "").strip()
    if not telefone:
        for qa in payload.get("questions_and_answers", []) or []:
            pergunta = (qa.get("question") or "").lower()
            if "telefone" in pergunta or "phone" in pergunta or "whatsapp" in pergunta:
                telefone = (qa.get("answer") or "").strip()
                break
    if telefone:
        return enderecos.normalizar(telefone)
    return "calendly:" + (payload.get("uri", "").rsplit("/", 1)[-1] or "desconhecido")


def _importar(db: Session, link: CalendlyLink, payload: dict) -> CalendlyRecebidoOut:
    evento = payload.get("scheduled_event") or {}
    inicio, fim = evento.get("start_time"), evento.get("end_time")
    if not inicio or not fim:
        return CalendlyRecebidoOut(importado=False, motivo="evento sem horário")
    inicio_dt, fim_dt = utc(datetime.fromisoformat(inicio)), utc(datetime.fromisoformat(fim))
    ref = payload.get("uri") or ""

    ja_existe = db.scalar(select(Appointment).where(Appointment.external_ref == ref))
    if ja_existe is not None:
        return CalendlyRecebidoOut(importado=False, motivo="evento já importado")

    servico = db.get(Service, link.service_id)
    if servico is None or not servico.ativo:
        return CalendlyRecebidoOut(importado=False, motivo="serviço da integração não está ativo")

    ap = Appointment(
        org_id=link.org_id,
        service_id=link.service_id,
        resource_id=link.resource_id,
        cliente_nome=(payload.get("name") or "Convidado do Calendly").strip(),
        cliente_telefone=_endereco_do_convidado(payload),
        # O horário vem do Calendly, não da duração do serviço daqui: quem
        # mandou no compromisso foi a outra plataforma.
        periodo=Range(inicio_dt, fim_dt),
        origem="calendly",
        external_ref=ref,
    )
    try:
        with db.begin_nested():
            db.add(ap)
            db.flush()
    except Exception as e:  # noqa: BLE001
        if "sem_double_booking" not in str(e):
            raise
        # O horário já está ocupado aqui. Não dá para recusar (o Calendly já
        # confirmou com o cliente) nem para sobrescrever: registra e avisa.
        log.warning("Calendly: conflito de horário na org %s (%s)", link.org_id, ref)
        return CalendlyRecebidoOut(
            importado=False, motivo="horário já ocupado nesta agenda — resolva com o cliente"
        )
    if link.cria_lembretes:
        booking.criar_lembretes(db, ap)
    db.commit()
    return CalendlyRecebidoOut(importado=True, motivo="compromisso criado")


def _cancelar(db: Session, payload: dict) -> CalendlyRecebidoOut:
    ap = db.scalar(select(Appointment).where(Appointment.external_ref == (payload.get("uri") or "")))
    if ap is None:
        return CalendlyRecebidoOut(importado=False, motivo="compromisso não estava aqui")
    if ap.status == "cancelado":
        return CalendlyRecebidoOut(importado=False, motivo="já estava cancelado")
    ap.status = "cancelado"
    db.commit()
    return CalendlyRecebidoOut(importado=True, motivo="compromisso cancelado")


@router.post(
    "/webhooks/calendly",
    response_model=CalendlyRecebidoOut,
    summary="Webhook do Calendly (público, assinatura verificada)",
    description=(
        "Recebe `invitee.created` e `invitee.canceled`. Sem credencial: quem "
        "autentica é a assinatura HMAC, que também diz de qual organização é o "
        "evento. Responde 200 mesmo quando nada é importado — um 4xx faria o "
        "Calendly reenviar indefinidamente."
    ),
    responses=respostas_publicas("ASSINATURA_INVALIDA"),
    openapi_extra={"security": []},
)
async def webhook(
    request: Request,
    calendly_webhook_signature: str = Header(default="", alias="Calendly-Webhook-Signature"),
) -> CalendlyRecebidoOut:
    corpo = await request.body()
    link = _org_do_evento(corpo, calendly_webhook_signature)
    if link is None:
        raise ApiError(
            code="ASSINATURA_INVALIDA",
            message="A assinatura deste webhook não confere com nenhuma integração ativa.",
            hint="Confira a signing key em PUT /integracoes/calendly e o relógio do servidor.",
            status_code=401,
        )
    import json

    dados = json.loads(corpo or b"{}")
    payload = dados.get("payload") or {}
    with SessionLocal() as db:
        sessao_org(db, link.org_id)
        if dados.get("event") == "invitee.created":
            return _importar(db, link, payload)
        if dados.get("event") == "invitee.canceled":
            return _cancelar(db, payload)
    return CalendlyRecebidoOut(importado=False, motivo=f"evento ignorado: {dados.get('event')}")
