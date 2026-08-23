# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""O conector repassa autoridade, não a possui — e traduz recusa em instrução."""

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from app import agenda, servidor, sessao

from .conftest import BEARER, ContextoFalso

TETO_DE_TOOLS = 15  # `00` §5.9


# ── A regra inegociável ──────────────────────────────────────────────────────


def test_o_conector_nao_tem_credencial_propria():
    """Se algum dia alguém adicionar uma AGENDA_SERVICE_KEY aqui "para
    simplificar", o conector vira um deputado confuso: um serviço com
    autoridade sobre a organização inteira executando pedidos de quem alcançar
    o endpoint. Toda a separação de papéis morreria num arquivo .env."""
    from app.config import Settings

    campos = set(Settings.model_fields)
    assert not {c for c in campos if "key" in c or "token" in c or "secret" in c}, (
        f"o conector ganhou um segredo próprio: {campos}"
    )


async def test_o_bearer_do_chamador_viaja_intacto(agenda_falsa, ctx):
    agenda_falsa.padrao = {"items": []}
    await servidor.agenda_admin_catalogo(ctx)
    for _, _, cabecalhos in agenda_falsa.chamadas:
        assert cabecalhos["authorization"] == BEARER


async def test_sem_credencial_a_tool_explica_em_vez_de_falhar_feio(agenda_falsa):
    ctx = ContextoFalso(autorizacao=None)
    with pytest.raises(ToolError) as erro:
        await servidor.agenda_admin_catalogo(ctx)
    assert "Authorization" in str(erro.value)


# ── A auditoria mora na agenda; o conector se identifica ─────────────────────


async def test_toda_chamada_se_identifica_para_a_auditoria(agenda_falsa, ctx):
    agenda_falsa.padrao = {"items": []}
    await servidor.agenda_admin_recurso_salvar(ctx, nome="Sala 2")
    escritas = [c for c in agenda_falsa.chamadas if c[0] == "POST"]
    assert escritas, "nada foi escrito"
    for _, _, cabecalhos in escritas:
        assert cabecalhos["x-mcp-server"] == "agenda-admin"
        assert cabecalhos["x-mcp-tool"] == "agenda_admin_recurso_salvar"
        # convenção do programa: toda escrita aceita Idempotency-Key
        assert cabecalhos["idempotency-key"]


async def test_leitura_nao_manda_chave_de_idempotencia(agenda_falsa, ctx):
    agenda_falsa.padrao = {"items": []}
    await servidor.agenda_admin_catalogo(ctx)
    for metodo, _, cabecalhos in agenda_falsa.chamadas:
        assert metodo == "GET"
        assert "idempotency-key" not in cabecalhos


# ── Falhar rápido e legível ──────────────────────────────────────────────────


async def test_a_sessao_e_validada_uma_vez_so(agenda_falsa, ctx):
    agenda_falsa.padrao = {"items": []}
    await servidor.agenda_admin_catalogo(ctx)
    await servidor.agenda_admin_grade_ver(ctx)
    eu = [c for c in agenda_falsa.chamadas if c[1] == "/credenciais/eu"]
    assert len(eu) == 1, "uma ida ao banco por tool seria o preço de nada"


async def test_credenciais_diferentes_nao_compartilham_a_validacao(agenda_falsa, ctx):
    agenda_falsa.padrao = {"items": []}
    await servidor.agenda_admin_grade_ver(ctx)
    await servidor.agenda_admin_grade_ver(ContextoFalso(autorizacao="Bearer agk_outro"))
    assert len([c for c in agenda_falsa.chamadas if c[1] == "/credenciais/eu"]) == 2


async def test_recusa_da_agenda_chega_ao_modelo_com_o_que_fazer(agenda_falsa, ctx):
    """Um 403 cru faria o modelo tentar de novo com outros argumentos, achando
    que errou o payload. O `hint` do contrato é a metade que corrige isso."""
    agenda_falsa.responder(
        "POST",
        "/resources",
        403,
        {
            "code": "ESCOPO_INSUFICIENTE",
            "message": "A credencial não tem o escopo 'agenda:admin'.",
            "hint": "Esta credencial tem ['agenda:read']. Funções administrativas exigem…",
            "retryable": False,
        },
    )
    with pytest.raises(ToolError) as erro:
        await servidor.agenda_admin_recurso_salvar(ctx, nome="Sala 2")
    assert "agenda:admin" in str(erro.value)
    assert "Esta credencial tem" in str(erro.value)


async def test_agenda_fora_do_ar_diz_que_nada_mudou(agenda_falsa, ctx, monkeypatch):
    async def cair(*_a, **_k):
        raise agenda.AgendaIndisponivel("conexão recusada")

    monkeypatch.setattr(agenda, "chamar", cair)
    sessao.limpar_cache()
    with pytest.raises(ToolError) as erro:
        await servidor.agenda_admin_recurso_salvar(ctx, nome="Sala 2")
    assert "nada foi alterado" in str(erro.value).lower()


# ── Criar-ou-alterar, sem CRUD ───────────────────────────────────────────────


async def test_salvar_sem_id_cria_e_com_id_altera(agenda_falsa, ctx):
    await servidor.agenda_admin_servico_salvar(ctx, nome="Corte", duracao_min=60)
    await servidor.agenda_admin_servico_salvar(ctx, service_id="abc", preco="90.00")
    metodos = [(m, r) for m, r, _ in agenda_falsa.chamadas if r != "/credenciais/eu"]
    assert ("POST", "/services") in metodos
    assert ("PATCH", "/services/abc") in metodos


async def test_alterar_so_manda_o_que_foi_informado(agenda_falsa, ctx, monkeypatch):
    """`_sem_nulos` é o que faz a alteração ser parcial: mandar `preco: null`
    apagaria o preço de um serviço que ninguém pediu para mudar."""
    corpos = []

    original = agenda.chamar

    async def espiar(metodo, rota, autorizacao, *, tool, corpo=None):
        corpos.append(corpo)
        return await original(metodo, rota, autorizacao, tool=tool, corpo=corpo)

    monkeypatch.setattr(agenda, "chamar", espiar)
    await servidor.agenda_admin_servico_salvar(ctx, service_id="abc", preco="90.00")
    assert corpos[-1] == {"preco": "90.00"}


async def test_criar_sem_o_minimo_e_recusado_antes_de_sair_daqui(agenda_falsa, ctx):
    with pytest.raises(ToolError) as erro:
        await servidor.agenda_admin_servico_salvar(ctx, preco="10.00")
    assert "duracao_min" in str(erro.value)
    assert not [c for c in agenda_falsa.chamadas if c[0] == "POST"]


async def test_grade_e_definida_de_uma_vez(agenda_falsa, ctx):
    await servidor.agenda_admin_grade_definir(
        ctx,
        resource_id="r1",
        janelas=[
            servidor.Janela(dia_semana=0, hora_inicio="09:00", hora_fim="12:00"),
            servidor.Janela(dia_semana=0, hora_inicio="13:00", hora_fim="18:00"),
        ],
    )
    metodo, rota, _ = agenda_falsa.chamadas[-1]
    assert (metodo, rota) == ("PUT", "/availability/rules?resource_id=r1")


async def test_catalogo_so_traz_desativados_quando_pedido(agenda_falsa, ctx):
    agenda_falsa.padrao = {"items": []}
    await servidor.agenda_admin_catalogo(ctx)
    rotas = [r for m, r, _ in agenda_falsa.chamadas if m == "GET"]
    assert not [r for r in rotas if "ativo=false" in r]

    agenda_falsa.chamadas.clear()
    await servidor.agenda_admin_catalogo(ctx, incluir_inativos=True)
    rotas = [r for m, r, _ in agenda_falsa.chamadas if m == "GET"]
    assert len([r for r in rotas if "ativo=false" in r]) == 2  # serviços e recursos
