"""Schemas Pydantic da API. Dinheiro trafega como string (numeric no banco);
horário sempre ISO 8601 com offset + label_humano na saída.
"""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from .tempo import exigir_aware, label_humano


class Pagina[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None


class _DinheiroOut:
    @field_serializer("preco", check_fields=False)
    def _preco_str(self, v: Decimal) -> str:
        return f"{v:.2f}"


# ── Serviços e recursos ──────────────────────────────────────────────────────


class ServiceIn(BaseModel):
    nome: str = Field(min_length=1)
    duracao_min: int = Field(gt=0)
    preco: Decimal = Field(default=Decimal("0"), ge=0)
    buffer_antes_min: int = Field(default=0, ge=0)
    buffer_depois_min: int = Field(default=0, ge=0)
    ativo: bool = True
    resource_ids: list[UUID] = []  # recursos exigidos (RF-01)


class ServiceOut(_DinheiroOut, BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str
    duracao_min: int
    preco: Decimal
    buffer_antes_min: int
    buffer_depois_min: int
    ativo: bool


class ServicePatch(BaseModel):
    """Alteração parcial: só os campos enviados mudam. Alterar duração não
    altera agendamentos já existentes (RF-01)."""

    nome: str | None = Field(default=None, min_length=1)
    duracao_min: int | None = Field(default=None, gt=0)
    preco: Decimal | None = Field(default=None, ge=0)
    buffer_antes_min: int | None = Field(default=None, ge=0)
    buffer_depois_min: int | None = Field(default=None, ge=0)
    ativo: bool | None = None
    resource_ids: list[UUID] | None = None  # None = não mexe; [] = remove vínculos


class ResourceIn(BaseModel):
    nome: str = Field(min_length=1)
    tipo: str | None = None
    ativo: bool = True


class ResourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str
    tipo: str | None
    ativo: bool


# ── Grade ────────────────────────────────────────────────────────────────────


class RuleIn(BaseModel):
    resource_id: UUID
    dia_semana: int = Field(ge=0, le=6, description="0=segunda … 6=domingo")
    hora_inicio: time
    hora_fim: time


class RulePatch(BaseModel):
    dia_semana: int | None = Field(default=None, ge=0, le=6)
    hora_inicio: time | None = None
    hora_fim: time | None = None


class RuleOut(RuleIn):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class BlockIn(BaseModel):
    resource_id: UUID
    inicio: datetime
    fim: datetime
    motivo: str | None = None

    @field_validator("inicio", "fim")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        return exigir_aware(v)


class BlockOut(BaseModel):
    id: UUID
    resource_id: UUID
    inicio: datetime
    fim: datetime
    motivo: str | None


# ── Slots ────────────────────────────────────────────────────────────────────


class SlotOut(BaseModel):
    inicio: datetime
    fim: datetime
    resource_id: UUID
    label_humano: str

    @classmethod
    def de_inicio(cls, inicio: datetime, duracao_min: int, resource_id: UUID) -> "SlotOut":
        from datetime import timedelta

        return cls(
            inicio=inicio,
            fim=inicio + timedelta(minutes=duracao_min),
            resource_id=resource_id,
            label_humano=label_humano(inicio),
        )


# ── Agendamentos ─────────────────────────────────────────────────────────────


class AppointmentIn(BaseModel):
    service_id: UUID
    inicio: datetime
    cliente_nome: str = Field(min_length=1)
    cliente_telefone: str = Field(min_length=8)
    resource_id: UUID | None = None  # sem informar: primeiro recurso livre do serviço
    origem: str = "agente"
    observacoes: str | None = None

    @field_validator("inicio")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        return exigir_aware(v, "inicio")

    @field_validator("origem")
    @classmethod
    def _origem(cls, v: str) -> str:
        if v not in ("agente", "cliente", "humano", "calendly"):
            raise ValueError("origem deve ser agente|cliente|humano|calendly")
        return v


class AppointmentOut(BaseModel):
    id: UUID
    service_id: UUID
    resource_id: UUID
    cliente_nome: str
    cliente_telefone: str
    inicio: datetime
    fim: datetime
    label_humano: str
    status: str
    origem: str
    risco_no_show: str | None = None
    observacoes: str | None = None
    series_id: UUID | None = None


class RecurrenceIn(BaseModel):
    """RF-15: série semanal ou quinzenal — deliberadamente sem RRULE completo.

    `inicio` é a primeira ocorrência (define dia da semana e hora). Informe
    `ocorrencias` OU `fim_em`, nunca os dois.
    """

    service_id: UUID
    inicio: datetime
    cliente_nome: str = Field(min_length=1)
    cliente_telefone: str = Field(min_length=8)
    frequencia: str = Field(description="semanal ou quinzenal")
    ocorrencias: int | None = Field(default=None, ge=2, le=52)
    fim_em: date | None = None
    resource_id: UUID | None = None
    origem: str = "agente"
    observacoes: str | None = None

    @field_validator("inicio")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        return exigir_aware(v, "inicio")

    @field_validator("frequencia")
    @classmethod
    def _frequencia(cls, v: str) -> str:
        if v not in ("semanal", "quinzenal"):
            raise ValueError("frequencia deve ser semanal ou quinzenal")
        return v

    @model_validator(mode="after")
    def _limite(self) -> "RecurrenceIn":
        if (self.ocorrencias is None) == (self.fim_em is None):
            raise ValueError("informe ocorrencias OU fim_em (exatamente um)")
        if self.fim_em is not None:
            if self.fim_em <= self.inicio.date():
                raise ValueError("fim_em precisa ser depois da primeira ocorrência")
            if (self.fim_em - self.inicio.date()).days > 370:
                raise ValueError("série limitada a 12 meses — use fim_em mais próximo")
        return self


class ConflitoOcorrencia(BaseModel):
    """Ocorrência que caiu em slot ocupado: a série não quebra (RF-15) —
    fica pendente com as 3 alternativas já propostas."""

    inicio: datetime
    label_humano: str
    alternativas: list[dict]


class RecurrenceOut(BaseModel):
    series_id: UUID
    frequencia: str
    criadas: list[AppointmentOut]
    conflitos: list[ConflitoOcorrencia]


class SeriesCancelIn(BaseModel):
    motivo: str
    confirmation_token: str | None = None


class RescheduleIn(BaseModel):
    novo_inicio: datetime
    motivo: str | None = None

    @field_validator("novo_inicio")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        return exigir_aware(v, "novo_inicio")


class CancelIn(BaseModel):
    motivo: str
    confirmation_token: str | None = None
