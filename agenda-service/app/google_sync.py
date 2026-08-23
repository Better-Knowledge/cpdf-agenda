"""RF-12 — a ponte entre a agenda e o Google Calendar.

Duas direções, com garantias deliberadamente diferentes:

**Push (agenda → Google), assíncrono.** Agendar não pode depender do Google
estar de pé. O compromisso é gravado, o evento de domínio é gravado junto na
mesma transação, e um job entrega depois com retry. É outbox clássico: se o
Google estiver fora do ar por uma hora, ninguém percebe além do atraso.

**Busy-read (Google → agenda), síncrono e degradável.** O motor de slots
pergunta ao Google o que já está ocupado na conta do prestador, com cache
curto. Google fora do ar → calcula só com os dados locais e registra aviso;
o pior caso é oferecer um horário que o prestador tinha reservado no Google,
que é exatamente o comportamento de antes da integração existir.
"""

import logging
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import crypto
from . import google_calendar as gcal
from .models import Appointment, DomainEvent, EventDelivery, GoogleCalendarLink, Service
from .sessao import SessionLocal, sessao_org, sessao_worker
from .tempo import agora_utc

log = logging.getLogger("agenda.google")

CONSUMIDOR = "google-calendar"
MAX_TENTATIVAS = 5
TIPOS = (
    "agenda.appointment.created",
    "agenda.appointment.rescheduled",
    "agenda.appointment.canceled",
)
CACHE_BUSY_SEGUNDOS = 60


# ── Credenciais ──────────────────────────────────────────────────────────────


def link_ativo(db: Session, org_id: UUID, resource_id: UUID) -> GoogleCalendarLink | None:
    return db.scalar(
        select(GoogleCalendarLink).where(
            GoogleCalendarLink.org_id == org_id,
            GoogleCalendarLink.resource_id == resource_id,
            GoogleCalendarLink.ativo,
            GoogleCalendarLink.revogado_em.is_(None),
        )
    )


def acesso(db: Session, link: GoogleCalendarLink) -> str:
    """Access token válido, renovando e persistindo quando faltam < 5 min.

    A renovação grava na mesma sessão do chamador: se ela falhar depois, o
    token novo continua válido no Google — perder o refresh_token seria o
    único erro irrecuperável aqui.
    """
    creds = gcal.Credenciais.de_dict(crypto.decifrar(link.credenciais))
    if not creds.vencido:
        return creds.access_token
    novas = gcal.Credenciais.de_resposta(gcal.renovar(creds.refresh_token), creds.refresh_token)
    link.credenciais = crypto.cifrar(novas.como_dict())
    db.commit()
    return novas.access_token


def desconectar_por_recusa(db: Session, link: GoogleCalendarLink, erro: str) -> None:
    """O Google recusou de forma definitiva (token revogado do lado de lá,
    escopo retirado). Marcar inativo é honesto: a tela mostra "reconecte" em
    vez de acumular erro silencioso a cada compromisso novo."""
    link.ativo = False
    db.commit()
    log.warning("conexão Google do recurso %s desativada: %s", link.resource_id, erro)


# ── Push ─────────────────────────────────────────────────────────────────────


def _proxima_tentativa(evento: DomainEvent, tentativas: int) -> datetime:
    """Backoff exponencial ancorado no evento (1, 2, 4, 8, 16 min).

    Ancorar em `occurred_at` em vez de guardar o instante da última tentativa
    troca uma coluna por uma conta — e a diferença prática é nenhuma, porque
    o job roda de minuto em minuto.
    """
    return evento.occurred_at + timedelta(minutes=2**tentativas)


def _entrega(db: Session, evento_id: int) -> EventDelivery:
    linha = db.get(EventDelivery, {"event_id": evento_id, "consumer": CONSUMIDOR})
    if linha is None:
        linha = EventDelivery(event_id=evento_id, consumer=CONSUMIDOR)
        db.add(linha)
    return linha


def _corpo(ap: Appointment, servico: Service) -> dict:
    return gcal.corpo_do_evento(
        titulo=gcal.titulo_do_compromisso(servico.nome, ap.cliente_nome),
        inicio=ap.periodo.lower,
        fim=ap.periodo.upper,
        descricao=gcal.descricao_do_compromisso(
            cliente=ap.cliente_nome, telefone=ap.cliente_telefone, inicio=ap.periodo.lower
        ),
    )


def aplicar(db: Session, evento: DomainEvent) -> str:
    """Reflete UM evento no Google. Devolve o que foi feito, para o log.

    Idempotente pelo estado, não pelo evento: olha o compromisso agora e o
    `google_event_id` que ele carrega. Reprocessar não duplica evento no
    calendário nem apaga o que deveria existir.
    """
    ap = db.get(Appointment, UUID(evento.payload["appointment_id"]))
    if ap is None:
        return "compromisso sumiu"
    link = link_ativo(db, ap.org_id, ap.resource_id)
    if link is None:
        return "recurso sem Google conectado"
    servico = db.get(Service, ap.service_id)
    token = acesso(db, link)

    if ap.status in ("cancelado",):
        if not ap.google_event_id:
            return "cancelado antes de existir no Google"
        gcal.remover_evento(token, link.calendar_id, ap.google_event_id)
        ap.google_event_id = None
        db.commit()
        return "evento removido"

    if ap.google_event_id:
        gcal.atualizar_evento(token, link.calendar_id, ap.google_event_id, _corpo(ap, servico))
        return "evento atualizado"

    ap.google_event_id = gcal.criar_evento(token, link.calendar_id, _corpo(ap, servico))
    db.commit()
    return "evento criado"


def processar_pendentes(limite: int = 50) -> int:
    """Job do push. Devolve quantos eventos foram entregues nesta rodada."""
    if not gcal.configurado():
        return 0
    agora = agora_utc()
    with SessionLocal() as db:
        sessao_worker(db)  # a varredura cruza orgs; cada entrega roda presa à sua
        candidatos = db.execute(
            select(DomainEvent, EventDelivery)
            .outerjoin(
                EventDelivery,
                (EventDelivery.event_id == DomainEvent.id)
                & (EventDelivery.consumer == CONSUMIDOR),
            )
            .where(
                DomainEvent.event_type.in_(TIPOS),
                EventDelivery.processed_at.is_(None),
                (EventDelivery.attempts.is_(None)) | (EventDelivery.attempts < MAX_TENTATIVAS),
            )
            .order_by(DomainEvent.id)
            .limit(limite)
        ).all()
        pendentes = [
            (e.id, e.org_id)
            for e, entrega in candidatos
            if entrega is None or _proxima_tentativa(e, entrega.attempts) <= agora
        ]

    entregues = 0
    for evento_id, org_id in pendentes:
        with SessionLocal() as db:
            sessao_worker(db)  # `event_deliveries` só é visível ao worker
            sessao_org(db, org_id)
            evento = db.get(DomainEvent, evento_id)
            entrega = _entrega(db, evento_id)
            try:
                resultado = aplicar(db, evento)
                entrega.processed_at = agora_utc()
                entrega.last_error = None
                entregues += 1
                log.info("google: evento %s → %s", evento_id, resultado)
            except gcal.GoogleIndisponivel as e:
                entrega.attempts += 1
                entrega.last_error = str(e)[:500]
                log.warning("google indisponível no evento %s (%s)", evento_id, e)
            except gcal.GoogleRecusou as e:
                # Recusa não melhora com repetição: encerra a entrega e
                # desconecta, para que a tela peça reconexão.
                entrega.attempts = MAX_TENTATIVAS
                entrega.processed_at = agora_utc()
                entrega.last_error = str(e)[:500]
                ap = db.get(Appointment, UUID(evento.payload["appointment_id"]))
                link = link_ativo(db, org_id, ap.resource_id) if ap else None
                if link is not None:
                    desconectar_por_recusa(db, link, str(e))
            db.commit()
    return entregues


# ── Busy-read ────────────────────────────────────────────────────────────────

# Cache de processo, curto: o motor de slots varre vários dias e recursos numa
# única requisição, e sem isto cada varredura viraria uma rajada de chamadas.
_cache: dict[tuple, tuple[datetime, list[tuple[datetime, datetime]]]] = {}


def limpar_cache() -> None:
    _cache.clear()


def ocupado_no_google(
    db: Session, org_id: UUID, resource_id: UUID, de: datetime, ate: datetime
) -> list[tuple[datetime, datetime]]:
    """Intervalos ocupados na conta do prestador. Falhou? Lista vazia + aviso.

    Degradar em silêncio seria pior do que degradar com log: o efeito é
    oferecer um horário que o prestador reservou no Google, e o operador
    precisa poder descobrir por quê.
    """
    if not gcal.configurado():
        return []
    chave = (resource_id, de, ate)
    agora = agora_utc()
    if (guardado := _cache.get(chave)) and guardado[0] > agora:
        return guardado[1]
    link = link_ativo(db, org_id, resource_id)
    if link is None:
        return []
    try:
        busy = gcal.livre_ocupado(acesso(db, link), link.calendar_id, de, ate)
    except gcal.GoogleIndisponivel as e:
        log.warning("busy-read degradado para cálculo local (%s)", e)
        return []
    except gcal.GoogleRecusou as e:
        desconectar_por_recusa(db, link, str(e))
        return []
    _cache[chave] = (agora + timedelta(seconds=CACHE_BUSY_SEGUNDOS), busy)
    return busy


def calendarios_disponiveis(access_token: str) -> list[dict]:
    """Só para a tela escolher o calendário de destino na conexão."""
    dados = gcal._pedir(
        "GET", f"{gcal.API}/users/me/calendarList", headers={"Authorization": f"Bearer {access_token}"}
    )
    return [
        {"id": c["id"], "nome": c.get("summary", c["id"]), "principal": c.get("primary", False)}
        for c in dados.get("items", [])
        if c.get("accessRole") in ("owner", "writer")
    ]
