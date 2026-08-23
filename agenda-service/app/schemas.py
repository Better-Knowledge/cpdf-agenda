# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

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


class ResourcePatch(BaseModel):
    """Alteração parcial: só os campos enviados mudam."""

    nome: str | None = Field(default=None, min_length=1)
    tipo: str | None = None
    ativo: bool | None = None


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


class JanelaSemana(BaseModel):
    """Uma janela de trabalho, sem id: na definição declarativa a grade é
    descrita inteira, não remendada janela a janela."""

    dia_semana: int = Field(ge=0, le=6, description="0=segunda … 6=domingo")
    hora_inicio: time
    hora_fim: time


class GradeSemanaIn(BaseModel):
    """A semana inteira de um recurso, como ela deve ficar.

    Declarativo em vez de CRUD por um motivo prático: quando um agente
    precisa listar, remover uma, criar duas e não esquecer nenhuma, ele erra.
    Aqui ele descreve o resultado e o servidor faz a diferença — atômico.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "janelas": [
                        {"dia_semana": 0, "hora_inicio": "09:00", "hora_fim": "12:00"},
                        {"dia_semana": 0, "hora_inicio": "13:00", "hora_fim": "18:00"},
                        {"dia_semana": 1, "hora_inicio": "09:00", "hora_fim": "18:00"},
                    ]
                }
            ]
        }
    )

    janelas: list[JanelaSemana] = Field(
        description="A semana como deve ficar. Lista vazia limpa a grade do recurso."
    )


class GradeSemanaOut(BaseModel):
    resource_id: UUID
    janelas: list[RuleOut]
    removidas: int = Field(description="Quantas janelas anteriores foram substituídas")


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
    risco_detalhe: dict | None = Field(
        default=None,
        description="Como o risco foi somado: pontos, fatores e explicação (IA-03 é auditável)",
    )
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


# ── Credenciais e papéis ─────────────────────────────────────────────────────


class QuemSouOut(BaseModel):
    """O que esta credencial é e o que ela pode. É o que permite a um agente
    descobrir sua própria autoridade antes de tentar uma ação que seria
    recusada — e o que o conector MCP usa para falhar rápido e legível."""

    org_id: UUID
    nome: str
    papel: str | None = Field(default=None, description="atendimento | operacao | administrativo")
    ator: str = Field(description="humano | agente")
    escopos: list[str]
    titular: str | None = Field(
        default=None,
        description="Cliente em nome de quem a credencial age; ausente em credencial administrativa",
    )


class CredencialIn(BaseModel):
    """Emissão de credencial de agente. Só quem tem `credenciais:admin`."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"nome": "Copiloto da recepção", "papel": "operacao"},
                {
                    "nome": "Bot do Telegram",
                    "papel": "atendimento",
                    "escopos": ["agenda:read", "agenda:write"],
                },
            ]
        }
    )

    nome: str = Field(min_length=1, description="Como esta credencial aparece na tela e no log")
    papel: str = Field(description="atendimento | operacao | administrativo")
    escopos: list[str] | None = Field(
        default=None,
        description=(
            "Ajuste fino. Ausente, usa os escopos do papel. O papel é só o preset — "
            "quem manda é esta lista."
        ),
    )


class CredencialOut(BaseModel):
    """A credencial como ela aparece na gestão. **Nunca** traz o token."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str
    papel: str
    escopos: list[str]
    prefixo: str = Field(description="Primeiros caracteres do token, só para identificar a linha")
    ativo: bool
    criada_em: datetime
    ultimo_uso_em: datetime | None = Field(
        default=None, description="Atualizado no máximo a cada 5 min, para não contender na linha"
    )
    revogada_em: datetime | None = None


class CredencialCriadaOut(CredencialOut):
    token: str = Field(
        description=(
            "O token em claro. Aparece UMA vez, nesta resposta: o banco guarda só o "
            "SHA-256. Perdeu, emita outra e revogue esta."
        )
    )


class RevogacaoOut(BaseModel):
    id: UUID
    revogada: bool = Field(description="false = já estava revogada (revogar é idempotente)")
    aviso: str = Field(
        description="A revogação leva até o TTL do cache de credenciais para valer em todo processo"
    )


# ── Fila de espera (RF-14) ───────────────────────────────────────────────────


class WaitlistIn(BaseModel):
    """Entrar na fila para uma JANELA, não para um horário: quem quer um
    horário específico e livre simplesmente agenda."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "service_id": "b3f0a1d4-2c5e-4f6a-8b7c-9d0e1f2a3b4c",
                    "cliente_nome": "Paula Andrade",
                    "cliente_telefone": "+5511998765432",
                    "janela_inicio": "2026-08-27T12:00:00-03:00",
                    "janela_fim": "2026-08-27T18:00:00-03:00",
                }
            ]
        }
    )

    service_id: UUID
    cliente_nome: str = Field(min_length=1)
    cliente_telefone: str = Field(
        min_length=3, description="E.164 no WhatsApp ou tg:<chat_id> no Telegram"
    )
    janela_inicio: datetime = Field(description="Começo da janela desejada, ISO 8601 com offset")
    janela_fim: datetime = Field(description="Fim da janela desejada, ISO 8601 com offset")
    resource_id: UUID | None = Field(
        default=None, description="Opcional: só aceita com este profissional/sala"
    )

    @field_validator("janela_inicio", "janela_fim")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        return exigir_aware(v)

    @model_validator(mode="after")
    def _ordem(self) -> "WaitlistIn":
        if self.janela_fim <= self.janela_inicio:
            raise ValueError("janela_fim precisa ser depois de janela_inicio")
        return self


class WaitlistOut(BaseModel):
    id: UUID
    service_id: UUID
    resource_id: UUID | None
    cliente_nome: str
    cliente_telefone: str
    janela_inicio: datetime
    janela_fim: datetime
    janela_humana: str = Field(description="A janela desejada em pt-BR, pronta para falar")
    status: str = Field(description="aguardando | ofertado | aceito | expirado | cancelado")
    posicao: int | None = Field(
        default=None, description="Posição na fila entre os que aguardam o mesmo serviço"
    )
    expira_em: datetime | None = Field(
        default=None, description="Quando a oferta em aberto expira (status=ofertado)"
    )
    slot_ofertado: datetime | None = Field(
        default=None, description="Horário exato proposto pela oferta em aberto"
    )
    avisos: list[str] = Field(
        default_factory=list,
        description="O que o prestador precisa saber — ex.: cliente em opt-out não recebe oferta",
    )


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


# ── Feed .ics (RF-11) ────────────────────────────────────────────────────────


class IcsTokenIn(BaseModel):
    """O feed é por recurso; sem `resource_id`, cobre a organização inteira."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"resource_id": "8b1f…", "modo": "completo"}],
        }
    )
    resource_id: UUID | None = Field(
        default=None, description="Recurso do feed. Omitido: todos os recursos da organização."
    )
    modo: str = Field(
        default="completo",
        description=(
            "`completo` mostra serviço e cliente no título; `privado` mostra só "
            "'Ocupado' — use quando a URL for parar num calendário compartilhado."
        ),
    )

    @field_validator("modo")
    @classmethod
    def _modo_conhecido(cls, v: str) -> str:
        if v not in ("completo", "privado"):
            raise ValueError("modo deve ser 'completo' ou 'privado'")
        return v


class IcsTokenOut(BaseModel):
    """A URL sai **redigida**: quem a obtém lê a agenda inteira do recurso.

    O valor completo aparece uma vez na criação e, depois, só em
    `POST /ics/tokens/{id}/revelar` — o mesmo tratamento que a `webhook_url`
    do canal recebe.
    """

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    resource_id: UUID | None = None
    modo: str
    url: str = Field(description="URL do feed, com o token redigido")
    revogado_em: datetime | None = None
    created_at: datetime


class IcsTokenCriadoOut(IcsTokenOut):
    url_completa: str = Field(
        description="Assine esta URL no Google/Apple Calendar. Recupere depois em /ics/tokens/{id}/revelar."
    )


# ── Google Calendar (RF-12) ──────────────────────────────────────────────────


class GoogleConectarIn(BaseModel):
    resource_id: UUID = Field(description="Recurso (profissional/sala) cuja agenda será espelhada")


class GoogleConectarOut(BaseModel):
    """A rota devolve a URL; quem navega até ela é o navegador do prestador.

    Não é redirect direto porque a chamada é autenticada por header — e header
    não sobrevive a um redirect iniciado pelo browser.
    """

    url: str = Field(description="Abra no navegador do prestador. Vale 10 minutos.")
    expira_em_segundos: int = 600


class GoogleConexaoOut(BaseModel):
    """Status da conexão. Os tokens **nunca** aparecem aqui: são write-only."""

    resource_id: UUID
    resource_nome: str
    calendar_id: str
    ativo: bool
    precisa_reconectar: bool = Field(
        description="true quando o Google recusou os tokens (revogados lá, ou escopo retirado)"
    )
    conectado_em: datetime


class GoogleDesconectadoOut(BaseModel):
    resource_id: UUID
    desconectado: bool = Field(description="false = já não havia conexão (é idempotente)")
    aviso: str


# ── Link público de auto-agendamento (RF-13) ─────────────────────────────────


class BookingLinkIn(BaseModel):
    """A caução é **configuração informativa** nesta fase: a página mostra o
    valor, e a cobrança via Pix é roadmap (§18). Nasce desligada."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"service_id": "9c1e…", "slug": "corte", "exige_caucao": False}]
        }
    )
    service_id: UUID
    resource_id: UUID | None = Field(
        default=None, description="Opcional: link de um profissional específico"
    )
    slug: str | None = Field(
        default=None,
        max_length=60,
        description="Pedaço final da URL. Omitido, é derivado do nome do serviço.",
    )
    exige_caucao: bool = False
    valor_caucao: Decimal | None = None


class BookingLinkPatch(BaseModel):
    ativo: bool | None = None
    exige_caucao: bool | None = None
    valor_caucao: Decimal | None = None


class BookingLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    service_id: UUID
    resource_id: UUID | None = None
    slug: str
    url: str = Field(description="Endereço para mandar ao cliente")
    ativo: bool
    exige_caucao: bool
    valor_caucao: Decimal | None = None
    created_at: datetime

    @field_serializer("valor_caucao")
    def _dinheiro(self, v: Decimal | None) -> str | None:
        return None if v is None else f"{v:.2f}"


class PaginaPublicaOut(BaseModel):
    """O que a página pública mostra antes de o cliente escolher horário.

    De propósito, o mínimo: nome e duração do serviço. Nada de recurso, nada
    de agenda — a página não é lugar de reconstruir a ocupação do prestador.
    """

    slug: str
    servico: str
    duracao_min: int
    preco: str
    exige_caucao: bool
    valor_caucao: str | None = None
    aviso_caucao: str | None = Field(
        default=None, description="Texto pronto para a página, quando há caução configurada"
    )


class AgendamentoPublicoIn(BaseModel):
    """Coleta mínima (LGPD §13): nome e um jeito de avisar. Nada além."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "cliente_nome": "Ana Prado",
                    "cliente_telefone": "+5511999998888",
                    "inicio": "2027-03-09T14:00:00-03:00",
                }
            ]
        }
    )
    cliente_nome: str = Field(min_length=2, max_length=120)
    cliente_telefone: str = Field(min_length=8, max_length=40)
    inicio: datetime

    @field_validator("inicio")
    @classmethod
    def _com_fuso(cls, v: datetime) -> datetime:
        return exigir_aware(v, "inicio")


class AgendamentoPublicoOut(BaseModel):
    """A confirmação devolve o combinado — e nada sobre o resto da agenda."""

    id: UUID
    servico: str
    inicio: datetime
    label_humano: str
    mensagem: str


# ── Calendly (RF-16) ─────────────────────────────────────────────────────────


class CalendlyConfigIn(BaseModel):
    """A chave de assinatura é write-only: entra aqui, some do banco cifrada,
    e nunca volta numa leitura."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "service_id": "9c1e…",
                    "resource_id": "6f1e…",
                    "chave_assinatura": "a-chave-do-webhook-no-Calendly",
                    "cria_lembretes": False,
                }
            ]
        }
    )
    service_id: UUID = Field(description="Serviço com que o agendamento importado entra")
    resource_id: UUID = Field(description="Recurso que fica ocupado pelo compromisso importado")
    chave_assinatura: str = Field(
        min_length=8,
        description="A signing key que o Calendly mostra ao criar a assinatura do webhook",
    )
    cria_lembretes: bool = Field(
        default=False,
        description=(
            "Padrão false: o Calendly já manda os lembretes dele, e dois lembretes "
            "para o mesmo horário é uma boa forma de irritar o cliente."
        ),
    )


class CalendlyConfigOut(BaseModel):
    service_id: UUID
    resource_id: UUID
    cria_lembretes: bool
    ativo: bool
    webhook_url: str = Field(description="Cadastre esta URL na assinatura do webhook no Calendly")
    created_at: datetime


class CalendlyRecebidoOut(BaseModel):
    """Resposta do webhook. Sempre 200 quando a assinatura confere — inclusive
    quando nada é importado: um 4xx faria o Calendly reenviar para sempre."""

    importado: bool
    motivo: str


# ── Métricas (T-10) ──────────────────────────────────────────────────────────


class MetricasOut(BaseModel):
    """Os números do PRD §4, no período pedido.

    Percentuais saem como número de 0 a 100 com uma casa — a tela não faz
    conta, só mostra. Quando o denominador é zero, o campo vem `None` em vez
    de `0`: "não houve base para calcular" e "deu zero" são coisas diferentes,
    e confundir as duas é como métrica engana.
    """

    de: date
    ate: date
    total: int
    por_status: dict[str, int]
    por_origem: dict[str, int]
    pct_por_conversa: float | None = Field(
        description="Agendamentos com origem `agente` sobre o total (alvo do §4: ≥ 90%)"
    )
    pct_no_show: float | None = Field(description="Faltas sobre os compromissos já passados")
    pct_confirmados: float | None = Field(
        description="Confirmados pelo cliente sobre os compromissos do período"
    )
    pct_ocupacao: float | None = Field(
        description="Horas agendadas sobre as horas de grade disponíveis no período"
    )
    cancelados: int
    fila_aguardando: int
    fila_atendida: int = Field(description="Pessoas que entraram na fila e acabaram agendando")
    narrativa: str = Field(description="Os mesmos números em uma frase, prontos para falar")
