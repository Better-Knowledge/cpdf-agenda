# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""O cliente HTTP da agenda — e a regra que este serviço existe para não quebrar.

**O conector não tem credencial própria.** Ele repassa, sem tocar, o
`Authorization` que o chamador apresentou. Não é economia de configuração: no
dia em que alguém lhe der uma `AGENDA_SERVICE_KEY` "para simplificar", ele
vira um deputado confuso — um serviço com autoridade sobre a organização
inteira executando pedidos de quem quer que alcance o endpoint MCP. Toda a
separação de papéis das etapas anteriores morreria num arquivo `.env`.

Corolário: **o conector nunca decide autorização.** Ele não olha escopo, não
compara papel, não filtra resposta. Quem recusa é a agenda, com o mesmo 403
que recusaria um `curl`. O que ele faz é traduzir a recusa para algo que um
modelo consiga ler e corrigir — o `hint` do contrato já é escrito para isso.
"""

import logging
import uuid
from typing import Any

import httpx

from .config import settings

log = logging.getLogger("agenda_admin_mcp.agenda")

SERVIDOR = "agenda-admin"
METODOS_DE_MUDANCA = {"POST", "PATCH", "PUT", "DELETE"}


class AgendaRecusou(Exception):
    """Erro de contrato da agenda ({code, message, hint, retryable})."""

    def __init__(self, status: int, corpo: dict[str, Any]):
        self.status = status
        self.code = corpo.get("code", "ERRO")
        self.message = corpo.get("message", "A agenda respondeu com erro.")
        self.hint = corpo.get("hint", "")
        self.extra = {c: v for c, v in corpo.items() if c not in {"code", "message", "hint", "retryable"}}
        super().__init__(f"{self.code}: {self.message}")

    def para_o_modelo(self) -> str:
        """A mensagem que o agente lê. O `hint` vem junto porque é a metade que
        diz o que fazer a seguir — e às vezes já traz a saída no payload."""
        partes = [self.message]
        if self.hint:
            partes.append(self.hint)
        return " ".join(partes)


class AgendaIndisponivel(Exception):
    pass


# Um cliente só, reaproveitado: o conector é um processo de longa duração e
# abrir conexão por chamada custaria um handshake em cada tool.
_cliente: httpx.AsyncClient | None = None


def cliente() -> httpx.AsyncClient:
    global _cliente
    if _cliente is None:
        _cliente = httpx.AsyncClient(base_url=settings().agenda_service_url, timeout=20)
    return _cliente


async def fechar() -> None:
    global _cliente
    if _cliente is not None:
        await _cliente.aclose()
        _cliente = None


async def chamar(
    metodo: str,
    rota: str,
    autorizacao: str,
    *,
    tool: str,
    corpo: Any | None = None,
) -> Any:
    cabecalhos = {
        "Authorization": autorizacao,
        # A auditoria mora na agenda (00 §5.8). Estes dois headers são o que
        # faz a linha do log dizer "agenda_admin_recurso_salvar" em vez de
        # "POST /resources" — a pergunta "o que o agente fez" respondida no
        # vocabulário de quem chamou.
        "X-MCP-Server": SERVIDOR,
        "X-MCP-Tool": tool,
    }
    if metodo in METODOS_DE_MUDANCA:
        # Uma chave nova por chamada, como faz a UI: o que a idempotência
        # protege aqui é o retry de rede, não a repetição deliberada — dois
        # bloqueios iguais pedidos de propósito devem virar dois bloqueios.
        cabecalhos["Idempotency-Key"] = str(uuid.uuid4())
    try:
        resposta = await cliente().request(metodo, rota, json=corpo, headers=cabecalhos)
    except httpx.HTTPError as e:
        raise AgendaIndisponivel(f"A agenda não respondeu ({e}).") from e

    try:
        dados = resposta.json()
    except ValueError:
        dados = {}
    if resposta.status_code >= 400:
        raise AgendaRecusou(resposta.status_code, dados if isinstance(dados, dict) else {})
    return dados
