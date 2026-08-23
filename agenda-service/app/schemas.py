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

from .contrato import Alternativa
from .tempo import exigir_aware, label_humano


class Pagina[T](BaseModel):
    items: list[T]
    next_cursor: str | None = Field(
        default=None,
        description="Presente quando há mais páginas — repita a chamada com cursor=<este valor>",
    )


class _DinheiroOut:
    @field_serializer("preco", check_fields=False)
    def _preco_str(self, v: Decimal) -> str:
        return f"{v:.2f}"


# ── Serviços e recursos ──────────────────────────────────────────────────────


class ServiceIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "nome": "Corte feminino",
                    "duracao_min": 60,
                    "preco": "80.00",
                    "buffer_depois_min": 10,
                    "resource_ids": ["6f1e0c2a-8f6e-4b9e-9d3a-0d5b2a7c9c02"],
                }
            ]
        }
    )

    nome: str = Field(min_length=1)
    duracao_min: int = Field(gt=0)
    preco: Decimal = Field(default=Decimal("0"), ge=0, description="String decimal, BRL")
    buffer_antes_min: int = Field(default=0, ge=0)
    buffer_depois_min: int = Field(default=0, ge=0)
    ativo: bool = True
    resource_ids: list[UUID] = []  # recursos exigidos (RF-01)


class ServiceOut(_DinheiroOut, BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "b3f0a1d4-2c5e-4f6a-8b7c-9d0e1f2a3b4c",
                    "nome": "Corte feminino",
                    "duracao_min": 60,
                    "preco": "80.00",
                    "buffer_antes_min": 0,
                    "buffer_depois_min": 10,
                    "ativo": True,
                }
            ]
        },
    )
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
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "resource_id": "6f1e0c2a-8f6e-4b9e-9d3a-0d5b2a7c9c02",
                    "dia_semana": 1,
                    "hora_inicio": "09:00",
                    "hora_fim": "18:00",
                }
            ]
        }
    )

    resource_id: UUID
    dia_semana: int = Field(ge=0, le=6, description="0=segunda … 6=domingo")
    hora_inicio: time = Field(description="Hora local America/Sao_Paulo")
    hora_fim: time = Field(description="Hora local America/Sao_Paulo")


class RulePatch(BaseModel):
    dia_semana: int | None = Field(default=None, ge=0, le=6)
    hora_inicio: time | None = None
    hora_fim: time | None = None


class RuleOut(RuleIn):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class BlockIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "resource_id": "6f1e0c2a-8f6e-4b9e-9d3a-0d5b2a7c9c02",
                    "inicio": "2026-09-07T00:00:00-03:00",
                    "fim": "2026-09-08T00:00:00-03:00",
                    "motivo": "Feriado — Independência",
                }
            ]
        }
    )

    resource_id: UUID
    inicio: datetime = Field(description="ISO 8601 com offset")
    fim: datetime = Field(description="ISO 8601 com offset")
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
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "inicio": "2026-08-27T15:30:00-03:00",
                    "fim": "2026-08-27T16:30:00-03:00",
                    "resource_id": "6f1e0c2a-8f6e-4b9e-9d3a-0d5b2a7c9c02",
                    "label_humano": "quinta, 27 de agosto, 15h30",
                }
            ]
        }
    )

    inicio: datetime
    fim: datetime
    resource_id: UUID
    label_humano: str = Field(description="Pronto para falar com o cliente, pt-BR")

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
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "service_id": "b3f0a1d4-2c5e-4f6a-8b7c-9d0e1f2a3b4c",
                    "inicio": "2026-08-27T15:30:00-03:00",
                    "cliente_nome": "Paula Andrade",
                    "cliente_telefone": "+5511998765432",
                    "origem": "agente",
                    "observacoes": "Prefere atendimento com a Júlia",
                }
            ]
        }
    )

    service_id: UUID
    inicio: datetime = Field(description="Um inicio devolvido por GET /slots (ISO 8601 com offset)")
    cliente_nome: str = Field(min_length=1)
    cliente_telefone: str = Field(
        min_length=3,
        description=(
            "Endereço do cliente no canal: E.164 no WhatsApp (+5511998765432) ou "
            "tg:<chat_id> no Telegram. É por ele que os lembretes saem."
        ),
    )
    resource_id: UUID | None = None  # sem informar: primeiro recurso livre do serviço
    origem: str = Field(default="agente", description="agente | cliente | humano | calendly")
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
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "0b6ff65e-4f2a-4c8d-9e1b-3a5c7d9f0e2a",
                    "service_id": "b3f0a1d4-2c5e-4f6a-8b7c-9d0e1f2a3b4c",
                    "resource_id": "6f1e0c2a-8f6e-4b9e-9d3a-0d5b2a7c9c02",
                    "cliente_nome": "Paula Andrade",
                    "cliente_telefone": "+5511998765432",
                    "inicio": "2026-08-27T15:30:00-03:00",
                    "fim": "2026-08-27T16:30:00-03:00",
                    "label_humano": "quinta, 27 de agosto, 15h30",
                    "status": "agendado",
                    "origem": "agente",
                    "risco_no_show": None,
                    "observacoes": None,
                    "series_id": None,
                }
            ]
        }
    )

    id: UUID
    service_id: UUID
    resource_id: UUID
    cliente_nome: str
    cliente_telefone: str
    inicio: datetime
    fim: datetime
    label_humano: str = Field(description="Pronto para falar com o cliente, pt-BR")
    status: str = Field(description="agendado | confirmado | cancelado | realizado | no_show")
    origem: str
    risco_no_show: str | None = Field(default=None, description="baixo | medio | alto (IA-03)")
    observacoes: str | None = None
    series_id: UUID | None = Field(default=None, description="Presente quando faz parte de uma série (RF-15)")


class RecurrenceIn(BaseModel):
    """RF-15: série semanal ou quinzenal — deliberadamente sem RRULE completo.

    `inicio` é a primeira ocorrência (define dia da semana e hora). Informe
    `ocorrencias` OU `fim_em`, nunca os dois.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "service_id": "b3f0a1d4-2c5e-4f6a-8b7c-9d0e1f2a3b4c",
                    "inicio": "2026-09-08T10:00:00-03:00",
                    "cliente_nome": "Paula Andrade",
                    "cliente_telefone": "+5511998765432",
                    "frequencia": "semanal",
                    "ocorrencias": 4,
                }
            ]
        }
    )

    service_id: UUID
    inicio: datetime
    cliente_nome: str = Field(min_length=1)
    cliente_telefone: str = Field(
        min_length=3, description="E.164 no WhatsApp ou tg:<chat_id> no Telegram"
    )
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
    alternativas: list[Alternativa] = Field(
        description="Ofereça-as ao cliente e agende a ocorrência com POST /appointments"
    )


class RecurrenceOut(BaseModel):
    series_id: UUID
    frequencia: str
    criadas: list[AppointmentOut]
    conflitos: list[ConflitoOcorrencia] = Field(
        description="Ocorrências que caíram em horário ocupado — pendentes, com alternativas"
    )


class SeriesCancelIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"motivo": "cliente encerrou o pacote"}]}
    )

    motivo: str
    confirmation_token: str | None = Field(
        default=None,
        description="Exigido para agentes: venha da resposta 409 CONFIRMACAO_NECESSARIA",
    )


class SerieCanceladaOut(BaseModel):
    series_id: UUID
    canceladas: int = Field(description="Quantas ocorrências futuras foram canceladas")


class RescheduleIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"novo_inicio": "2026-08-28T09:00:00-03:00", "motivo": "cliente pediu"}
            ]
        }
    )

    novo_inicio: datetime = Field(description="Um inicio devolvido por GET /slots")
    motivo: str | None = None

    @field_validator("novo_inicio")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        return exigir_aware(v, "novo_inicio")


class CancelIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"motivo": "cliente pediu"}]})

    motivo: str
    confirmation_token: str | None = Field(
        default=None,
        description="Exigido para agentes: venha da resposta 409 CONFIRMACAO_NECESSARIA",
    )


# ── Saídas narradas e de manutenção ──────────────────────────────────────────


class AgendaDiaOut(BaseModel):
    data: date
    total: int
    narrativa: str = Field(
        description="O dia em linguagem clara, uma linha por compromisso — pronto para o agente falar"
    )
    compromissos: list[AppointmentOut]


class HistoricoOut(BaseModel):
    acao: str = Field(description="criado | reagendado | cancelado | confirmado | no_show")
    de: datetime | None = Field(default=None, description="Início anterior (reagendamento)")
    para: datetime | None = Field(default=None, description="Início novo (reagendamento)")
    origem: str | None = Field(default=None, description="Quem fez: humano | agente | cliente")
    motivo: str | None = None
    em: datetime


class RemocaoRegraOut(BaseModel):
    id: UUID
    removida: bool = Field(description="false = já não existia (remoção é idempotente)")


class RemocaoBloqueioOut(BaseModel):
    id: UUID
    removido: bool = Field(description="false = já não existia (remoção é idempotente)")


# ── Canal de WhatsApp (T-09 — proxy para o canal-service) ────────────────────


class CanalConfigIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "summary": "Telegram (o mais simples de testar)",
                    "value": {
                        "driver": "telegram",
                        "numero": "@minha_agenda_bot",
                        "instancia": "agenda-da-aula",
                        "credenciais": {"bot_token": "123456789:AAE…"},
                    },
                },
                {
                    "summary": "WhatsApp via Evolution (self-host)",
                    "value": {
                        "driver": "evolution",
                        "numero": "+5511900000000",
                        "instancia": "minha-org",
                        "credenciais": {
                            "server_url": "http://evolution_api:8080",
                            "apikey": "…",
                        },
                        "confirmo_numero_dedicado": True,
                    },
                },
            ]
        }
    )

    driver: str = Field(
        description="telegram | evolution | zapi | meta — trocar é só configuração"
    )
    numero: str = Field(
        min_length=3,
        description="WhatsApp: número DEDICADO em E.164. Telegram: @usuario do bot",
    )
    instancia: str = Field(min_length=1, description="Identificador da instância no driver")
    credenciais: dict[str, str] = Field(
        description="Write-only: cifradas no canal, nunca voltam em resposta ou log"
    )
    confirmo_numero_dedicado: bool = Field(
        default=False,
        description=(
            "O produto recusa número pessoal — declare que o número é dedicado. "
            "Não se aplica ao Telegram: um bot já é identidade separada"
        ),
    )


class CanalConfigCriadaOut(BaseModel):
    driver: str
    numero: str
    ativo: bool
    webhook_url: str = Field(
        description="URL (com segredo rotativo) que o driver chama — aparece só aqui"
    )


class CanalConfigOut(BaseModel):
    configurado: bool
    driver: str | None = None
    numero: str | None = None
    instancia: str | None = None
    ativo: bool = False
    webhook_url: str | None = None


class CanalConexaoOut(BaseModel):
    estado: str = Field(description="conectado | aguardando_qr | desconectado | desconhecido")
    qr_base64: str | None = Field(
        default=None, description="Data URI do QR — presente quando estado=aguardando_qr"
    )
    detalhe: str | None = None


class CanalTemplateIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "nome": "lembrete_24h",
                    "corpo": "Olá {{nome}}! Lembrete: {{servico}} {{data_hora}}. Responda SIM para confirmar ou SAIR para não receber avisos.",
                }
            ]
        }
    )

    nome: str = Field(min_length=1, description="Mesmo nome → nova versão (IA-02)")
    corpo: str = Field(min_length=1, description="Texto com {{variaveis}}")
    aprovado_meta: bool = False


class CanalTemplateOut(BaseModel):
    id: UUID
    nome: str
    corpo: str
    versao: int
    aprovado_meta: bool
    ativo: bool


class CanalOptoutOut(BaseModel):
    telefone: str = Field(description="Endereço no canal: E.164 ou tg:<chat_id>")
    origem: str | None = Field(default=None, description="palavra_chave | pedido_humano")
    em: str


class RemocaoOptoutOut(BaseModel):
    telefone: str
    removido: bool
