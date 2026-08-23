# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""O catálogo de tools é interface: o modelo escolhe pela descrição.

Estes testes tratam nome e texto como contrato, não como comentário. Uma tool
que não diz o escopo que exige leva o agente a tentar e falhar; uma tool
administrativa que aparecesse no servidor de atendimento derrubaria a
separação inteira.
"""

import asyncio

import pytest

from app.servidor import mcp

TETO = 15  # `00` §5.9 — acima disso o modelo passa a escolher mal


@pytest.fixture(scope="module")
def tools():
    return asyncio.run(mcp.list_tools())


def test_cabe_no_teto_do_programa(tools):
    assert len(tools) == 11
    assert len(tools) <= TETO


def test_toda_tool_e_do_dominio_administrativo(tools):
    """O prefixo não é estética: quando um cliente MCP conecta os dois
    servidores, é o que deixa 'cancelar' administrativo distinguível do
    'cancelar' de atendimento na lista que o modelo lê."""
    assert all(t.name.startswith("agenda_admin_") for t in tools)


ESCOPOS = (
    "agenda:read", "agenda:write", "agenda:cancel", "agenda:operacao",
    "agenda:admin", "canal:admin", "credenciais:admin",
)


def test_toda_tool_declara_o_escopo_que_exige(tools):
    """Sem isso o agente descobre a própria falta de autoridade tentando —
    e um 403 no meio de uma sequência ele costuma ler como erro de payload."""
    for t in tools:
        assert t.description, f"{t.name} sem descrição"
        assert any(e in t.description for e in ESCOPOS), f"{t.name} não nomeia escopo nenhum"


def test_nenhuma_tool_emite_ou_revoga_credencial(tools):
    """A porta que fica fechada: uma tool que distribui autoridade é a peça que
    transforma um token vazado em acesso permanente."""
    nomes = {t.name for t in tools}
    assert "agenda_admin_credenciais_listar" in nomes
    assert not {n for n in nomes if "credenciais" in n} - {"agenda_admin_credenciais_listar"}


def test_nenhuma_tool_atende_cliente_final(tools):
    """Agendar, remarcar e confirmar para um cliente são do outro servidor, com
    a outra credencial. Aqui não existem — a fronteira é topologia."""
    nomes = " ".join(t.name for t in tools)
    for proibido in ("agendar", "remarcar", "confirmar", "reagendar"):
        assert proibido not in nomes


def test_cancelar_avisa_que_e_irreversivel(tools):
    (cancelar,) = [t for t in tools if t.name == "agenda_admin_cancelar"]
    texto = cancelar.description.lower()
    assert "não tem volta" in texto or "irrevers" in texto
    assert "confirmação" in texto


def test_as_tools_de_escrita_pedem_o_estado_final(tools):
    """Declarativo em vez de CRUD: `salvar` cria-ou-altera, `grade_definir`
    substitui a semana. É o que evita o roteiro em que o modelo esquece um
    passo no meio."""
    nomes = {t.name for t in tools}
    assert {"agenda_admin_servico_salvar", "agenda_admin_recurso_salvar"} <= nomes
    (grade,) = [t for t in tools if t.name == "agenda_admin_grade_definir"]
    assert "substitui" in grade.description


def test_o_dia_nao_e_confundido_com_busca_de_horario(tools):
    """Erro clássico de agente: usar a agenda do dia para achar vaga livre. A
    descrição desarma isso explicitamente."""
    (dia,) = [t for t in tools if t.name == "agenda_admin_dia"]
    assert "não" in dia.description.lower() and "livre" in dia.description.lower()


def test_os_tres_prompts_do_prd_existem():
    """§14.3. Prompt é roteiro, não automação — e os três roteiros terminam
    devolvendo texto para uma pessoa decidir, nunca executando."""
    import asyncio

    from app.servidor import mcp

    prompts = asyncio.run(mcp.list_prompts())
    assert {p.name for p in prompts} == {
        "agenda_do_dia",
        "remarcar_semana",
        "confirmar_pendentes",
    }


def test_o_roteiro_de_remarcar_para_antes_de_agir():
    """O prompt mais perigoso do conjunto: sem esta instrução, o modelo
    remarcaria a semana inteira de clientes reais por conta própria."""
    from app.servidor import remarcar_semana

    texto = remarcar_semana(de="2027-03-15", ate="2027-03-19")
    assert "pare aí" in texto
    assert "sem meu OK" in texto
