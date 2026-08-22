"""Schemas Pydantic da API. Dinheiro trafega como string (numeric no banco);
horário sempre ISO 8601 com offset + label_humano na saída.
"""

from datetime import datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

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
