# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Uma agenda de mentira, servida em memória.

O que estes testes cobrem é o **conector**: as rotas que ele monta, os headers
que ele repassa, a tradução da recusa e o fluxo de confirmação. O que a agenda
faz com aquilo já é testado no `agenda-service` — repetir aqui só criaria duas
verdades sobre a mesma regra.
"""

import os
from dataclasses import dataclass, field
from typing import Any

os.environ.setdefault("APP_ENV", "dev")

import httpx  # noqa: E402
import pytest  # noqa: E402

IDENTIDADE = {
    "org_id": "3f6e0000-0000-4000-8000-0000000000aa",
    "nome": "MCP da recepção",
    "papel": "administrativo",
    "ator": "agente",
    "escopos": ["agenda:admin", "agenda:cancel", "agenda:operacao", "agenda:read", "agenda:write"],
    "titular": None,
}

BEARER = "Bearer agk_token-de-teste"


@dataclass
class AgendaFalsa:
    """Registra o que o conector pediu e devolve o que mandarmos."""

    chamadas: list[tuple[str, str, dict]] = field(default_factory=list)
    respostas: dict[tuple[str, str], list[tuple[int, Any]]] = field(default_factory=dict)
    padrao: Any = field(default_factory=dict)

    def responder(self, metodo: str, caminho: str, status: int, corpo: Any) -> None:
        """Enfileira uma resposta. Chamadas repetidas à mesma rota consomem a
        fila em ordem e a última resposta vale dali em diante — é o que deixa
        escrever "pede confirmação, depois cancela" sem remendar o transporte."""
        self.respostas.setdefault((metodo, caminho), []).append((status, corpo))

    async def __call__(self, scope, receive, send):
        metodo, caminho = scope["method"], scope["path"]
        query = scope.get("query_string", b"").decode()
        cabecalhos = {k.decode(): v.decode() for k, v in scope["headers"]}
        self.chamadas.append((metodo, caminho + (f"?{query}" if query else ""), cabecalhos))

        if caminho == "/credenciais/eu":
            status, corpo = 200, IDENTIDADE
        else:
            fila = self.respostas.get((metodo, caminho))
            if not fila:
                status, corpo = 200, self.padrao
            else:
                status, corpo = fila.pop(0) if len(fila) > 1 else fila[0]

        import json

        dados = json.dumps(corpo).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": dados})


@pytest.fixture()
def agenda_falsa(monkeypatch):
    from app import agenda, sessao

    falsa = AgendaFalsa()
    cliente = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=falsa), base_url="http://agenda-de-teste"
    )
    monkeypatch.setattr(agenda, "cliente", lambda: cliente)
    sessao.limpar_cache()
    yield falsa
    sessao.limpar_cache()


@dataclass
class ContextoFalso:
    """O mínimo de `Context` que as tools usam: headers, capacidades e elicit."""

    autorizacao: str | None = BEARER
    sabe_confirmar: bool = False
    resposta_da_pessoa: Any = None
    perguntas: list[str] = field(default_factory=list)

    @property
    def headers(self) -> dict[str, str] | None:
        return {"authorization": self.autorizacao} if self.autorizacao else {}

    @property
    def client_capabilities(self):
        return type("Caps", (), {"elicitation": {} if self.sabe_confirmar else None})()

    async def elicit(self, mensagem: str, schema):
        self.perguntas.append(mensagem)
        return self.resposta_da_pessoa


@pytest.fixture()
def ctx() -> ContextoFalso:
    return ContextoFalso()
