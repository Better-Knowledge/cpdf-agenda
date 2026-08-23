# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""O caminho real: cliente MCP → Streamable HTTP → tool → agenda.

Os outros testes chamam as funções direto, com um `Context` de mentira. Este
sobe o app ASGI e fala o protocolo: é o que prova que o `Authorization` da
conexão MCP chega ao header que a agenda lê — a peça de que tudo o mais
depende e que nenhum teste de unidade tocaria.
"""

from contextlib import asynccontextmanager

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .conftest import BEARER

URL = "http://conector-de-teste/mcp"


@pytest.fixture()
def app_mcp(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    from app.config import settings

    settings.cache_clear()
    from app.main import criar_app

    return criar_app()


@asynccontextmanager
async def conectado(app_mcp, autorizacao: str | None):
    """Tudo numa tarefa só: os escopos de cancelamento do anyio não sobrevivem
    a entrar num contexto e sair em outro — que é o que um fixture async faria.

    O `lifespan` entra aqui porque é onde vive o gerenciador de sessões do SDK;
    sem ele toda requisição morre com "task group is not initialized", que é
    exatamente o que aconteceria num deploy que servisse o app sem lifespan.
    """
    cabecalhos = {"Authorization": autorizacao} if autorizacao else {}
    async with app_mcp.router.lifespan_context(app_mcp):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app_mcp),
            base_url="http://conector-de-teste",
            headers=cabecalhos,
        ) as http:
            async with streamable_http_client(URL, http_client=http) as (leitura, escrita):
                async with ClientSession(leitura, escrita) as sessao:
                    inicio = await sessao.initialize()
                    yield sessao, inicio


async def test_o_bearer_da_conexao_chega_a_agenda(app_mcp, agenda_falsa):
    agenda_falsa.padrao = {"items": []}
    async with conectado(app_mcp, BEARER) as (sessao, _):
        resultado = await sessao.call_tool("agenda_listar_servicos", {})

    assert not resultado.is_error, resultado.content
    assert agenda_falsa.chamadas, "a tool não chegou a falar com a agenda"
    for _, _, cabecalhos in agenda_falsa.chamadas:
        assert cabecalhos["authorization"] == BEARER


async def test_o_catalogo_de_tools_chega_pelo_protocolo(app_mcp):
    async with conectado(app_mcp, BEARER) as (sessao, inicio):
        tools = (await sessao.list_tools()).tools

    assert inicio.server_info.name == "agenda"
    # As instruções dizem ao modelo como conduzir — inclusive o que não fazer
    assert "por extenso" in (inicio.instructions or "")
    assert "fila de espera" in (inicio.instructions or "")
    assert len(tools) == 8


async def test_conexao_sem_credencial_e_recusada_com_instrucao(app_mcp, agenda_falsa):
    """Não é 500 nem silêncio: a mensagem diz onde arranjar a chave."""
    async with conectado(app_mcp, None) as (sessao, _):
        resultado = await sessao.call_tool("agenda_listar_servicos", {})

    assert resultado.is_error
    assert "ats_" in resultado.content[0].text
    assert agenda_falsa.chamadas == []
