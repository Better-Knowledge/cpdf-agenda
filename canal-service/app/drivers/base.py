"""Contrato dos drivers de WhatsApp (`00` §4.8).

A assimetria que a interface carrega desde o dia 1: na Meta, mensagem ativa
exige template pré-aprovado; nos não-oficiais é texto livre. Por isso quem
decide "pode texto livre?" é o driver (`suporta_texto_livre_ativo`) — e a
regra template-first vale para todos: o canal SEMPRE renderiza um template
para mensagem ativa, mesmo quando o driver a entrega como texto.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx


@dataclass(frozen=True)
class ResultadoEnvio:
    driver_message_id: str | None
    custo: float | None = None


@dataclass(frozen=True)
class MensagemInbound:
    instancia: str  # identifica a org (channel_configs.credenciais.instancia)
    telefone: str
    texto: str
    message_id: str
    timestamp: datetime | None = None


class DriverCanal(ABC):
    nome: str
    suporta_texto_livre_ativo: bool

    def __init__(self, http: httpx.Client | None = None):
        self.http = http or httpx.Client(timeout=15)

    @abstractmethod
    def enviar_texto(
        self, credenciais: dict[str, Any], telefone: str, texto: str
    ) -> ResultadoEnvio:
        """Entrega texto já renderizado (sessão ou template renderizado)."""

    @abstractmethod
    def enviar_template_oficial(
        self, credenciais: dict[str, Any], telefone: str, template_nome: str,
        variaveis: dict[str, Any],
    ) -> ResultadoEnvio:
        """Só faz sentido em driver oficial (Meta): template pré-aprovado por nome."""

    @abstractmethod
    def normalizar_inbound(self, payload: dict[str, Any]) -> MensagemInbound | None:
        """Webhook cru do driver → mensagem normalizada. None = evento sem texto
        (status de entrega, mídia não tratada, etc.)."""


class ErroDriver(Exception):
    def __init__(self, mensagem: str, *, retryable: bool):
        super().__init__(mensagem)
        self.retryable = retryable
