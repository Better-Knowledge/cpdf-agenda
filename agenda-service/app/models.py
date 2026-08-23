"""Modelo de dados do agenda-service — espelho do PRD §10.

A verdade sobre conflito de horário NÃO está aqui: vive na constraint
`EXCLUDE USING gist` criada na migration 0001. Os models só descrevem colunas.
"""

import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSTZRANGE, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import DateTime


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True)}


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Service(Base):
    __tablename__ = "services"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID]
    nome: Mapped[str] = mapped_column(Text)
    duracao_min: Mapped[int]
    preco: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    buffer_antes_min: Mapped[int] = mapped_column(Integer, default=0)
    buffer_depois_min: Mapped[int] = mapped_column(Integer, default=0)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    __table_args__ = (CheckConstraint("duracao_min > 0", name="duracao_positiva"),)


class Resource(Base):
    __tablename__ = "resources"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID]
    nome: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class ServiceResource(Base):
    __tablename__ = "service_resources"
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("services.id"), primary_key=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resources.id"), primary_key=True)


class AvailabilityRule(Base):
    __tablename__ = "availability_rules"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID]
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resources.id"))
    dia_semana: Mapped[int]  # 0=segunda … 6=domingo (convenção Python weekday)
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fim: Mapped[time] = mapped_column(Time)
    __table_args__ = (
        CheckConstraint("dia_semana between 0 and 6", name="dia_semana_valido"),
        CheckConstraint("hora_fim > hora_inicio", name="janela_valida"),
    )


class AvailabilityBlock(Base):
    __tablename__ = "availability_blocks"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID]
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resources.id"))
    periodo = mapped_column(TSTZRANGE, nullable=False)
    motivo: Mapped[str | None] = mapped_column(Text)


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID]
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("services.id"))
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resources.id"))
    company_id: Mapped[uuid.UUID | None]  # vínculo CRM opcional
    contact_id: Mapped[uuid.UUID | None]
    cliente_nome: Mapped[str] = mapped_column(Text)  # denormalizado: agenda opera sem CRM
    cliente_telefone: Mapped[str] = mapped_column(Text)
    periodo = mapped_column(TSTZRANGE, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="agendado")
    risco_no_show: Mapped[str | None] = mapped_column(Text)
    risco_detalhe: Mapped[dict | None] = mapped_column(JSONB)
    origem: Mapped[str] = mapped_column(Text, default="agente")
    observacoes: Mapped[str | None] = mapped_column(Text)
    task_id: Mapped[uuid.UUID | None]
    series_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recurrence_series.id"))
    google_event_id: Mapped[str | None] = mapped_column(Text)
    external_ref: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    __table_args__ = (
        CheckConstraint(
            "status in ('agendado','confirmado','cancelado','realizado','no_show')",
            name="status_valido",
        ),
    )


class AppointmentHistory(Base):
    __tablename__ = "appointment_history"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    appointment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments.id"))
    acao: Mapped[str] = mapped_column(Text)  # criado|reagendado|cancelado|confirmado|no_show
    de = mapped_column(TSTZRANGE)
    para = mapped_column(TSTZRANGE)
    origem: Mapped[str | None] = mapped_column(Text)
    motivo: Mapped[str | None] = mapped_column(Text)
    por: Mapped[uuid.UUID | None]
    em: Mapped[datetime] = mapped_column(server_default=text("now()"))


class Reminder(Base):
    __tablename__ = "reminders"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    org_id: Mapped[uuid.UUID]
    appointment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments.id"))
    tipo: Mapped[str] = mapped_column(Text)  # confirmacao|lembrete_24h|lembrete_2h|risco_alto
    agendado_para: Mapped[datetime]
    enviado_em: Mapped[datetime | None]
    canal_message_id: Mapped[int | None] = mapped_column(BigInteger)
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    erro: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("appointment_id", "tipo", name="lembrete_unico"),)


class IcsToken(Base):
    __tablename__ = "ics_tokens"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID]
    resource_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resources.id"))
    token: Mapped[str] = mapped_column(Text, unique=True)
    modo: Mapped[str] = mapped_column(Text, default="completo")  # completo|privado
    revogado_em: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class GoogleCalendarLink(Base):
    __tablename__ = "google_calendar_links"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID]
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resources.id"))
    calendar_id: Mapped[str] = mapped_column(Text)
    credenciais: Mapped[dict] = mapped_column(JSONB)  # tokens OAuth cifrados; write-only na API
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    revogado_em: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    __table_args__ = (UniqueConstraint("org_id", "resource_id", name="um_link_por_recurso"),)


class BookingLink(Base):
    __tablename__ = "booking_links"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID]
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("services.id"))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resources.id"))
    slug: Mapped[str] = mapped_column(Text, unique=True)
    exige_caucao: Mapped[bool] = mapped_column(Boolean, default=False)
    valor_caucao: Mapped[float | None] = mapped_column(Numeric(14, 2))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class WaitlistEntry(Base):
    __tablename__ = "waitlist"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID]
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("services.id"))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resources.id"))
    cliente_nome: Mapped[str] = mapped_column(Text)
    cliente_telefone: Mapped[str] = mapped_column(Text)
    janela_desejada = mapped_column(TSTZRANGE, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="aguardando")
    ofertado_em: Mapped[datetime | None]
    expira_em: Mapped[datetime | None]
    slot_ofertado = mapped_column(TSTZRANGE)  # o horário exato que a oferta propôs
    resource_ofertado: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resources.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    __table_args__ = (
        CheckConstraint(
            "status in ('aguardando','ofertado','aceito','expirado','cancelado')",
            name="status_fila_valido",
        ),
    )


class RecurrenceSeries(Base):
    __tablename__ = "recurrence_series"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID]
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("services.id"))
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resources.id"))
    frequencia: Mapped[str] = mapped_column(Text)  # semanal|quinzenal
    dia_semana: Mapped[int]
    hora_inicio: Mapped[time] = mapped_column(Time)
    fim_em: Mapped[date | None] = mapped_column(Date)
    ocorrencias: Mapped[int | None]
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    __table_args__ = (
        CheckConstraint("frequencia in ('semanal','quinzenal')", name="frequencia_valida"),
        CheckConstraint("dia_semana between 0 and 6", name="dia_semana_serie_valido"),
    )


class DomainEvent(Base):
    """Barramento do programa (`00` §4.4) — polling do worker, sem fila externa."""

    __tablename__ = "domain_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    org_id: Mapped[uuid.UUID]
    event_type: Mapped[str] = mapped_column(Text)  # ex.: agenda.appointment.created
    payload: Mapped[dict] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    processed_at: Mapped[datetime | None]
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class IdempotencyKey(Base):
    """Toda escrita aceita Idempotency-Key; repetição devolve a mesma resposta."""

    __tablename__ = "idempotency_keys"
    org_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    chave: Mapped[str] = mapped_column(Text, primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text, primary_key=True)
    resposta: Mapped[dict] = mapped_column(JSONB)
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class AgentCredential(Base):
    """Credencial de agente — a autoridade que uma integração tem nesta org.

    O `papel` é só o preset que preencheu os escopos na criação; quem manda é
    a coluna `escopos`, que o administrador ajusta credencial a credencial.

    O token em claro nunca é gravado: guardamos o SHA-256. Entropia de 32
    bytes aleatórios dispensa bcrypt/argon2 — não há superfície de dicionário,
    e um hash lento custaria latência em toda requisição. O `prefixo` serve só
    para a tela identificar a linha; nunca é chave de busca.
    """

    __tablename__ = "agent_credentials"
    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID]
    nome: Mapped[str] = mapped_column(Text)  # "Agente do WhatsApp", "Copiloto da recepção"
    papel: Mapped[str] = mapped_column(Text)  # atendimento | operacao | administrativo
    escopos: Mapped[list[str]] = mapped_column(ARRAY(Text))
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    prefixo: Mapped[str] = mapped_column(Text)  # primeiros caracteres, para a UI
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criada_em: Mapped[datetime] = mapped_column(server_default=text("now()"))
    ultimo_uso_em: Mapped[datetime | None]
    revogada_em: Mapped[datetime | None]
    __table_args__ = (
        CheckConstraint(
            "papel in ('atendimento','operacao','administrativo')", name="papel_valido"
        ),
    )


class AgentAuditLog(Base):
    """`00` §5.8 — toda ação de agente é rastreável.

    A pergunta que esta tabela existe para responder: "quem cancelou esse
    horário, o agente ou uma pessoa — e em nome de quem?". Por isso `titular`,
    que não está no schema do doc base: sem ele não dá para responder a
    segunda metade.
    """

    __tablename__ = "agent_audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    org_id: Mapped[uuid.UUID]
    mcp_server: Mapped[str] = mapped_column(Text)  # agenda | agenda-admin
    tool_name: Mapped[str] = mapped_column(Text)  # nome da tool, ou "METODO /rota"
    client_id: Mapped[uuid.UUID | None]  # agent_credentials.id
    actor: Mapped[str | None] = mapped_column(Text)  # nome da credencial
    titular: Mapped[str | None] = mapped_column(Text)  # em nome de qual cliente
    args_hash: Mapped[str | None] = mapped_column(Text)  # hash, nunca o valor cru
    resultado: Mapped[str] = mapped_column(Text)  # ok | erro | recusado
    error_code: Mapped[str | None] = mapped_column(Text)
    latencia_ms: Mapped[int | None] = mapped_column(Integer)
    confirmado_por: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
