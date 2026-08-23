# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Schema do canal-service (PRD §10 — contrato em `00` §4.8)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import DateTime


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True)}


class ChannelConfig(Base):
    """Driver é configuração por organização — trocar não muda uma linha de código."""

    __tablename__ = "channel_configs"
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    driver: Mapped[str] = mapped_column(Text)  # evolution|zapi|telegram|meta
    credenciais: Mapped[dict] = mapped_column(JSONB)  # cifrado (Fernet); write-only na API
    numero: Mapped[str] = mapped_column(Text)  # WhatsApp: número DEDICADO; Telegram: @bot
    instancia: Mapped[str] = mapped_column(Text)  # roteia o webhook inbound até a org
    webhook_token: Mapped[str] = mapped_column(Text)  # segredo do webhook (PRD §9) — na URL
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        CheckConstraint(
            "driver in ('evolution','zapi','telegram','meta')", name="driver_valido"
        ),
        UniqueConstraint("driver", "instancia", name="instancia_unica_por_driver"),
    )


class ChannelTemplate(Base):
    __tablename__ = "channel_templates"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID]
    nome: Mapped[str] = mapped_column(Text)  # lembrete_24h, confirmacao, ...
    corpo: Mapped[str] = mapped_column(Text)  # com {{variaveis}}
    versao: Mapped[int] = mapped_column(Integer, default=1)
    aprovado_meta: Mapped[bool] = mapped_column(Boolean, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("org_id", "nome", "versao", name="template_versionado"),)


class ChannelMessage(Base):
    __tablename__ = "channel_messages"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    org_id: Mapped[uuid.UUID]
    direcao: Mapped[str] = mapped_column(Text)  # saida|entrada
    # Endereço do cliente NESTE canal: E.164 no WhatsApp, `tg:<chat_id>` no Telegram
    telefone: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str | None] = mapped_column(Text)  # sessao|template
    template_id: Mapped[uuid.UUID | None]
    corpo_renderizado: Mapped[str | None] = mapped_column(Text)
    driver: Mapped[str] = mapped_column(Text)
    driver_message_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pendente")
    custo: Mapped[float | None] = mapped_column(Numeric(10, 4))
    erro: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    __table_args__ = (
        CheckConstraint("direcao in ('saida','entrada')", name="direcao_valida"),
        CheckConstraint("tipo in ('sessao','template')", name="tipo_valido"),
        CheckConstraint(
            "status in ('pendente','enviada','entregue','lida','falha')", name="status_valido"
        ),
        UniqueConstraint("driver", "driver_message_id", name="inbound_idempotente"),
    )


class ChannelOptout(Base):
    """Opt-out determinístico: "SAIR" registra aqui ANTES de qualquer LLM."""

    __tablename__ = "channel_optouts"
    org_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    telefone: Mapped[str] = mapped_column(Text, primary_key=True)
    origem: Mapped[str | None] = mapped_column(Text)  # palavra_chave|pedido_humano
    em: Mapped[datetime] = mapped_column(server_default=text("now()"))
