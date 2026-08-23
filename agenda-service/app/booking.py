"""Regras de agendamento: carregar ocupação, criar/reagendar/cancelar.

A invariante anti-double-booking mora na constraint `sem_double_booking`
(migration 0001). Aqui só se traduz a violação em erro conversável com as
3 alternativas no payload — o agente se recupera sem uma segunda chamada.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .errors import ApiError, NaoEncontrado
from .models import (
    Appointment,
    AppointmentHistory,
    AvailabilityBlock,
    AvailabilityRule,
    DomainEvent,
    Reminder,
    Resource,
    Service,
    ServiceResource,
)
from .slots_engine import RegraGrade, alternativas_proximas, calcular_slots
from .tempo import agora_utc, label_humano, utc

REGUA_LEMBRETES = [  # RF-05: padrão da régua; por-org fica na etapa de configurações
    ("confirmacao", timedelta(0)),
    ("lembrete_24h", timedelta(hours=-24)),
    ("lembrete_2h", timedelta(hours=-2)),
]


def carregar_servico(db: Session, org_id: uuid.UUID, service_id: uuid.UUID) -> Service:
    servico = db.scalar(
        select(Service).where(Service.id == service_id, Service.org_id == org_id)
    )
    if servico is None or not servico.ativo:
        raise NaoEncontrado("Serviço", str(service_id))
    return servico


def recursos_do_servico(db: Session, servico: Service) -> list[Resource]:
    """Recursos exigidos pelo serviço; sem vínculo, qualquer recurso ativo da org."""
    vinculados = db.scalars(
        select(Resource)
        .join(ServiceResource, ServiceResource.resource_id == Resource.id)
        .where(ServiceResource.service_id == servico.id, Resource.ativo)
    ).all()
    if vinculados:
        return list(vinculados)
    return list(
        db.scalars(select(Resource).where(Resource.org_id == servico.org_id, Resource.ativo))
    )


def _ocupacao(db: Session, resource_id: uuid.UUID, de: datetime, ate: datetime):
    """Bloqueios + agendamentos vivos do recurso no intervalo (em UTC).

    Quando a integração Google (RF-12) chegar, o busy-read entra aqui —
    o motor de slots não sabe que a integração existe.
    """
    janela = Range(utc(de), utc(ate))
    ocupados: list[tuple[datetime, datetime]] = []
    for bloco in db.scalars(
        select(AvailabilityBlock).where(
            AvailabilityBlock.resource_id == resource_id,
            AvailabilityBlock.periodo.overlaps(janela),
        )
    ):
        ocupados.append((bloco.periodo.lower, bloco.periodo.upper))
    # Compromisso existente ocupa o período dele + os buffers do serviço dele
    # (RF-02: a grade desconta duração + buffers dos dois lados).
    for compromisso, servico in db.execute(
        select(Appointment, Service)
        .join(Service, Service.id == Appointment.service_id)
        .where(
            Appointment.resource_id == resource_id,
            Appointment.status.in_(("agendado", "confirmado")),
            Appointment.periodo.overlaps(janela),
        )
    ):
        ocupados.append(
            (
                compromisso.periodo.lower - timedelta(minutes=servico.buffer_antes_min),
                compromisso.periodo.upper + timedelta(minutes=servico.buffer_depois_min),
            )
        )
    return ocupados


def slots_do_recurso(
    db: Session,
    servico: Service,
    resource_id: uuid.UUID,
    de: datetime,
    ate: datetime,
    limite: int = 50,
) -> list[datetime]:
    cfg = settings()
    regras = [
        RegraGrade(r.dia_semana, r.hora_inicio, r.hora_fim)
        for r in db.scalars(
            select(AvailabilityRule).where(AvailabilityRule.resource_id == resource_id)
        )
    ]
    if not regras:
        return []
    return calcular_slots(
        duracao_min=servico.duracao_min,
        buffer_antes_min=servico.buffer_antes_min,
        buffer_depois_min=servico.buffer_depois_min,
        regras=regras,
        ocupados=_ocupacao(db, resource_id, de, ate),
        de=de,
        ate=ate,
        agora=agora_utc(),
        granularidade_min=cfg.granularidade_min,
        antecedencia_minima_min=cfg.antecedencia_minima_min,
        limite=limite,
    )


def erro_slot_indisponivel(
    db: Session, servico: Service, resource_id: uuid.UUID, alvo: datetime
) -> ApiError:
    """SLOT_INDISPONIVEL com as 3 alternativas mais próximas já no payload."""
    slots = slots_do_recurso(
        db, servico, resource_id, de=alvo - timedelta(days=3), ate=alvo + timedelta(days=7)
    )
    alternativas = alternativas_proximas(slots, alvo, n=3)
    lista = [
        {"inicio": s.isoformat(), "label_humano": label_humano(s)} for s in alternativas
    ]
    legivel = " · ".join(a["label_humano"] for a in lista) or "nenhuma na próxima semana"
    return ApiError(
        code="SLOT_INDISPONIVEL",
        message="O horário pedido já está ocupado ou fora da grade.",
        hint=f"Ofereça estas alternativas ao cliente: {legivel}.",
        status_code=409,
        extra={"alternativas": lista},
    )


def _historico(db: Session, ap: Appointment, acao: str, **kw) -> None:
    db.add(AppointmentHistory(appointment_id=ap.id, acao=acao, **kw))


def _evento(db: Session, ap: Appointment, tipo: str) -> None:
    db.add(
        DomainEvent(
            org_id=ap.org_id,
            event_type=tipo,
            payload={
                "appointment_id": str(ap.id),
                "service_id": str(ap.service_id),
                "resource_id": str(ap.resource_id),
                "inicio": ap.periodo.lower.isoformat(),
                "status": ap.status,
            },
        )
    )


def gerar_ocorrencias(
    inicio: datetime,
    frequencia: str,
    ocorrencias: int | None,
    fim_em,
) -> list[datetime]:
    """Datas da série (RF-15), em hora de parede America/Sao_Paulo — o passo é
    em dias corridos sobre a data local, então uma eventual volta do DST muda
    o offset, nunca o horário combinado com o cliente."""
    from .tempo import TZ

    local = inicio.astimezone(TZ)
    passo = timedelta(days=7 if frequencia == "semanal" else 14)
    datas: list[datetime] = []
    atual = local
    while True:
        if ocorrencias is not None and len(datas) >= ocorrencias:
            break
        if fim_em is not None and atual.date() > fim_em:
            break
        datas.append(atual)
        proxima_data = (atual + passo).date()
        atual = datetime.combine(proxima_data, local.time(), tzinfo=TZ)
    return datas


def criar_lembretes(db: Session, ap: Appointment) -> None:
    inicio = ap.periodo.lower
    agora = agora_utc()
    for tipo, delta in REGUA_LEMBRETES:
        quando = agora if tipo == "confirmacao" else inicio + delta
        if quando >= agora:  # não agenda lembrete no passado
            db.add(
                Reminder(
                    org_id=ap.org_id, appointment_id=ap.id, tipo=tipo, agendado_para=quando
                )
            )


def criar_appointment(
    db: Session,
    org_id: uuid.UUID,
    servico: Service,
    resource_id: uuid.UUID,
    inicio: datetime,
    cliente_nome: str,
    cliente_telefone: str,
    origem: str,
    observacoes: str | None = None,
    series_id: uuid.UUID | None = None,
    external_ref: str | None = None,
) -> Appointment:
    fim = inicio + timedelta(minutes=servico.duracao_min)
    ap = Appointment(
        org_id=org_id,
        service_id=servico.id,
        resource_id=resource_id,
        cliente_nome=cliente_nome,
        cliente_telefone=cliente_telefone,
        periodo=Range(utc(inicio), utc(fim)),
        origem=origem,
        observacoes=observacoes,
        series_id=series_id,
        external_ref=external_ref,
    )
    try:
        # Savepoint: o conflito desfaz SÓ esta inserção — numa série (RF-15),
        # as ocorrências já criadas na mesma transação sobrevivem.
        with db.begin_nested():
            db.add(ap)
            db.flush()  # dispara a constraint sem_double_booking agora
    except IntegrityError as e:
        if "sem_double_booking" in str(e.orig):
            raise erro_slot_indisponivel(db, servico, resource_id, inicio) from e
        raise
    _historico(db, ap, "criado", para=ap.periodo, origem=origem)
    _evento(db, ap, "agenda.appointment.created")
    criar_lembretes(db, ap)
    return ap


def reagendar(
    db: Session, ap: Appointment, servico: Service, novo_inicio: datetime, origem: str,
    motivo: str | None,
) -> Appointment:
    """Atômico (RF-06): o UPDATE troca o período na mesma transação — a
    constraint valida o novo slot e o antigo é liberado junto, ou nada muda."""
    anterior = ap.periodo
    novo_fim = novo_inicio + timedelta(minutes=servico.duracao_min)
    try:
        with db.begin_nested():
            ap.periodo = Range(utc(novo_inicio), utc(novo_fim))
            ap.status = "agendado"  # reagendou: confirmação anterior não vale mais
            db.flush()
    except IntegrityError as e:
        db.refresh(ap)  # devolve o objeto ao estado persistido (nada mudou)
        if "sem_double_booking" in str(e.orig):
            raise erro_slot_indisponivel(db, servico, ap.resource_id, novo_inicio) from e
        raise
    _historico(db, ap, "reagendado", de=anterior, para=ap.periodo, origem=origem, motivo=motivo)
    _evento(db, ap, "agenda.appointment.rescheduled")
    # lembretes antigos morrem; a régua renasce para o novo horário
    for r in db.scalars(
        select(Reminder).where(Reminder.appointment_id == ap.id, Reminder.enviado_em.is_(None))
    ):
        db.delete(r)
    db.flush()
    criar_lembretes(db, ap)
    return ap
