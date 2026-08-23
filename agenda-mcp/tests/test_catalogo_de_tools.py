# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""O catálogo é interface: o que o modelo lê antes de escolher.

Estes testes tratam as descrições como contrato. Uma tool sem escopo
declarado, ou com nome fora do PRD §14.1, é uma regressão de produto — não
de estilo.
"""

import asyncio

from app.servidor import mcp

TOOLS_DO_PRD = {
    "agenda_listar_servicos",
    "agenda_consultar_slots",
    "agenda_meu_dia",
    "agenda_agendar",
    "agenda_reagendar",
    "agenda_confirmar",
    "agenda_fila_espera",
    "agenda_cancelar",
}

ESCOPOS = ("agenda:read", "agenda:write", "agenda:cancel")


def _tools():
    return asyncio.run(mcp.list_tools())


def test_sao_exatamente_as_oito_do_prd():
    assert {t.name for t in _tools()} == TOOLS_DO_PRD


def test_nenhuma_tool_administrativa_existe_aqui():
    """A separação é topologia, não disciplina: o que não existe não pode ser
    chamado por engano nem por injeção vinda da mensagem do cliente."""
    nomes = {t.name for t in _tools()}
    proibidas = ("salvar", "grade", "bloqueio", "credenciais", "admin")
    assert not [n for n in nomes if any(p in n for p in proibidas)]


def test_toda_tool_declara_o_escopo_que_exige():
    for tool in _tools():
        assert any(e in (tool.description or "") for e in ESCOPOS), tool.name


def test_cancelar_avisa_que_e_irreversivel_e_pede_humano():
    (cancelar,) = [t for t in _tools() if t.name == "agenda_cancelar"]
    descricao = cancelar.description or ""
    assert "não tem volta" in descricao
    assert "confirmação humana" in descricao


def test_consultar_slots_ensina_a_conduzir_a_conversa():
    """A tool mais chamada do sistema: a descrição dela é onde o comportamento
    do agente é definido de fato."""
    (slots,) = [t for t in _tools() if t.name == "agenda_consultar_slots"]
    descricao = slots.description or ""
    assert "sempre antes" in descricao
    assert "label_humano" in descricao
    assert "fila de espera" in descricao  # vazio não é ponto final
    assert "adivinhar" in descricao  # data ambígua vira pergunta
