# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Gestão de credenciais pela API — e a linha que ela não atravessa.

O bootstrap continua na CLI. O que estas rotas dão é o dia a dia: emitir para
um agente novo, ver quem usou quando, revogar. A regra que sobrevive a tudo:
`credenciais:admin` não é concedível por rota, porque uma credencial capaz de
emitir outra sobrevive à própria revogação.
"""

import uuid

import pytest

from app.auth import credencial_atual, limpar_cache
from app.main import app

from .conftest import credencial_falsa, integracao

pytestmark = integracao


@pytest.fixture(autouse=True)
def cache_limpo():
    limpar_cache()
    yield
    limpar_cache()


@pytest.fixture()
def como_administrativo(org_id):
    """Papel administrativo NÃO tem `credenciais:admin` — de propósito."""
    app.dependency_overrides[credencial_atual] = credencial_falsa(
        org_id, "administrativo", ator="agente", nome="MCP administrativo"
    )
    yield
    app.dependency_overrides.pop(credencial_atual, None)


def _emitir(client, nome="Bot do Telegram", papel="atendimento", escopos=None):
    corpo = {"nome": nome, "papel": papel}
    if escopos is not None:
        corpo["escopos"] = escopos
    return client.post("/credenciais", json=corpo)


def test_o_token_aparece_uma_vez_e_funciona(client, banco_migrado, catalogo):
    resposta = _emitir(client)
    assert resposta.status_code == 201, resposta.text
    criada = resposta.json()
    token = criada["token"]
    assert token.startswith("agk_")
    assert criada["escopos"] == ["agenda:read", "agenda:write"]

    autorizacao = {"Authorization": f"Bearer {token}"}
    assert client.get("/services", headers=autorizacao).status_code == 200
    # atendimento não alcança a operação — o preset entrou de fato na linha
    assert client.get("/agenda/day?date=2026-08-27", headers=autorizacao).status_code == 403


def test_a_listagem_nunca_devolve_o_token(client, banco_migrado):
    token = _emitir(client).json()["token"]
    linhas = client.get("/credenciais").json()
    assert len(linhas) == 1
    assert "token" not in linhas[0]
    assert token not in repr(linhas)
    assert linhas[0]["prefixo"] == token[:10]


def test_escopos_ajustados_a_mao_valem_mais_que_o_papel(client, banco_migrado):
    """O papel é preset; quem manda é a coluna `escopos`."""
    criada = _emitir(client, papel="operacao", escopos=["agenda:read"]).json()
    assert criada["escopos"] == ["agenda:read"]
    autorizacao = {"Authorization": f"Bearer {criada['token']}"}
    assert client.get("/services", headers=autorizacao).status_code == 200
    assert client.post("/resources", json={"nome": "x"}, headers=autorizacao).status_code == 403


def test_credenciais_admin_nao_e_delegavel_por_rota(client, banco_migrado):
    """A porta que fica fechada: um token que emite tokens sobreviveria à
    própria revogação, e a revogação é a única defesa contra vazamento."""
    resposta = _emitir(client, papel="administrativo", escopos=["agenda:read", "credenciais:admin"])
    assert resposta.status_code == 403
    assert resposta.json()["code"] == "ESCOPO_NAO_DELEGAVEL"
    assert client.get("/credenciais").json() == []


def test_papel_e_escopo_desconhecidos_sao_recusados(client, banco_migrado):
    assert _emitir(client, papel="dono-de-tudo").status_code == 422
    assert _emitir(client, escopos=["agenda:tudo"]).status_code == 422


def test_revogar_derruba_a_credencial(client, banco_migrado):
    criada = _emitir(client).json()
    autorizacao = {"Authorization": f"Bearer {criada['token']}"}
    assert client.get("/services", headers=autorizacao).status_code == 200

    revogacao = client.delete(f"/credenciais/{criada['id']}")
    assert revogacao.status_code == 200
    assert revogacao.json()["revogada"] is True
    assert "30 segundos" in revogacao.json()["aviso"]  # o preço do cache, explícito

    assert client.get("/services", headers=autorizacao).status_code == 401
    # A linha continua existindo: o log de auditoria aponta para ela.
    ((linha,),) = [client.get("/credenciais").json()]
    assert linha["revogada_em"] is not None and linha["ativo"] is False


def test_revogar_e_idempotente(client, banco_migrado):
    criada = _emitir(client).json()
    assert client.delete(f"/credenciais/{criada['id']}").json()["revogada"] is True
    assert client.delete(f"/credenciais/{criada['id']}").json()["revogada"] is False
    assert client.delete(f"/credenciais/{uuid.uuid4()}").status_code == 404


def test_administrativo_nao_gere_credenciais(client, banco_migrado, como_administrativo):
    """O agente do MCP configura a plataforma, mas não distribui autoridade."""
    for metodo, rota, corpo in [
        ("get", "/credenciais", None),
        ("post", "/credenciais", {"nome": "x", "papel": "atendimento"}),
        ("delete", f"/credenciais/{uuid.uuid4()}", None),
    ]:
        chamada = getattr(client, metodo)
        resposta = chamada(rota, json=corpo) if corpo is not None else chamada(rota)
        assert resposta.status_code == 403, f"{metodo.upper()} {rota}"
        assert resposta.json()["code"] == "ESCOPO_INSUFICIENTE"


def test_credencial_de_outra_org_nao_e_vista_nem_revogada(client, banco_migrado, org_id):
    from app.admin_cli import emitir as emitir_cli

    alheia = uuid.uuid4()
    emitir_cli(alheia, "Bot de outra empresa", "administrativo")
    _emitir(client, nome="O meu")

    minhas = client.get("/credenciais").json()
    assert [c["nome"] for c in minhas] == ["O meu"]

    from app.models import AgentCredential
    from app.sessao import SessionLocal, sessao_worker

    with SessionLocal() as db:
        sessao_worker(db)
        outra = db.query(AgentCredential).filter_by(org_id=alheia).one()
    assert client.delete(f"/credenciais/{outra.id}").status_code == 404
