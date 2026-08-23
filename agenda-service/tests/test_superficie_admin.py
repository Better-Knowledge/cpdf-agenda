# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Etapa 4 — o que a equipe precisa para operar a plataforma por conversa.

Sem estas rotas, um agente administrativo consegue criar mas não corrigir:
dá para cadastrar um recurso e nunca renomeá-lo, montar uma grade e só
desmontá-la janela a janela. O buraco não é de segurança, é de utilidade —
e é o que faz a alternativa por agente valer menos que a tela.
"""

import pytest

from app.auth import credencial_atual
from app.main import app

from .conftest import credencial_falsa, integracao

pytestmark = integracao


@pytest.fixture()
def como_atendimento(org_id):
    app.dependency_overrides[credencial_atual] = credencial_falsa(
        org_id, "atendimento", ator="agente", titular="+5511999998888", nome="Bot do canal"
    )
    yield
    app.dependency_overrides.pop(credencial_atual, None)


# ── Recursos: alterar e desativar ────────────────────────────────────────────


def test_recurso_pode_ser_renomeado(client, catalogo):
    rid = catalogo["recurso"]["id"]
    resposta = client.patch(f"/resources/{rid}", json={"nome": "Sala Azul"})
    assert resposta.status_code == 200
    assert resposta.json()["nome"] == "Sala Azul"
    assert resposta.json()["tipo"] == "sala"  # o que não foi enviado não muda


def test_desativar_recurso_e_reversivel(client, catalogo):
    """Soft delete, como em serviços: agendamentos apontam para o id, e apagar
    de verdade deixaria compromissos órfãos."""
    rid = catalogo["recurso"]["id"]
    assert client.delete(f"/resources/{rid}").json()["ativo"] is False
    assert [r["id"] for r in client.get("/resources").json()["items"]] == []

    assert client.patch(f"/resources/{rid}", json={"ativo": True}).json()["ativo"] is True
    assert [r["id"] for r in client.get("/resources").json()["items"]] == [rid]


def test_desativar_recurso_e_idempotente(client, catalogo):
    rid = catalogo["recurso"]["id"]
    assert client.delete(f"/resources/{rid}").status_code == 200
    assert client.delete(f"/resources/{rid}").status_code == 200


def test_recurso_de_outra_org_nao_existe(client):
    import uuid

    assert client.patch(f"/resources/{uuid.uuid4()}", json={"nome": "x"}).status_code == 404
    assert client.delete(f"/resources/{uuid.uuid4()}").status_code == 404


# ── Grade declarativa ────────────────────────────────────────────────────────


def _semana(client, rid, janelas):
    return client.put(f"/availability/rules?resource_id={rid}", json={"janelas": janelas})


def test_definir_grade_substitui_a_semana_inteira(client, catalogo):
    """O catálogo do teste já monta seg–sex 9h–18h; a definição declarativa
    troca as cinco por duas sem que ninguém precise listar e remover."""
    rid = catalogo["recurso"]["id"]
    resposta = _semana(
        client,
        rid,
        [
            {"dia_semana": 0, "hora_inicio": "09:00", "hora_fim": "12:00"},
            {"dia_semana": 0, "hora_inicio": "13:00", "hora_fim": "18:00"},
        ],
    )
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["removidas"] == 5
    assert len(corpo["janelas"]) == 2

    grade = client.get(f"/availability/rules?resource_id={rid}").json()
    assert [(j["dia_semana"], j["hora_inicio"]) for j in grade] == [(0, "09:00:00"), (0, "13:00:00")]


def test_semana_vazia_limpa_a_grade(client, catalogo):
    rid = catalogo["recurso"]["id"]
    assert _semana(client, rid, []).json()["removidas"] == 5
    assert client.get(f"/availability/rules?resource_id={rid}").json() == []


def test_janela_invertida_e_recusada_sem_tocar_na_grade(client, catalogo):
    """Atômico: a grade antiga sobrevive inteira a um payload inválido."""
    rid = catalogo["recurso"]["id"]
    resposta = _semana(
        client, rid, [{"dia_semana": 0, "hora_inicio": "18:00", "hora_fim": "09:00"}]
    )
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "PERIODO_INVALIDO"
    assert len(client.get(f"/availability/rules?resource_id={rid}").json()) == 5


def test_janelas_sobrepostas_sao_recusadas(client, catalogo):
    """09–12 e 11–14 no mesmo dia é engano. A união silenciosa esconderia o
    erro; o nome dos dois horários no erro deixa o agente corrigir sozinho."""
    rid = catalogo["recurso"]["id"]
    resposta = _semana(
        client,
        rid,
        [
            {"dia_semana": 2, "hora_inicio": "09:00", "hora_fim": "12:00"},
            {"dia_semana": 2, "hora_inicio": "11:00", "hora_fim": "14:00"},
        ],
    )
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "PERIODO_INVALIDO"
    assert "sobrep" in resposta.json()["message"]


def test_grade_de_recurso_inexistente_e_404(client):
    import uuid

    assert _semana(client, uuid.uuid4(), []).status_code == 404


def test_definir_grade_nao_mexe_na_grade_de_outro_recurso(client, catalogo):
    outro = client.post("/resources", json={"nome": "Sala 2", "tipo": "sala"}).json()
    _semana(client, outro["id"], [{"dia_semana": 3, "hora_inicio": "08:00", "hora_fim": "10:00"}])
    assert len(client.get(f"/availability/rules?resource_id={catalogo['recurso']['id']}").json()) == 5


# ── Nada disso é atendimento ─────────────────────────────────────────────────


def test_atendimento_nao_administra_o_catalogo(client, catalogo, como_atendimento):
    rid = catalogo["recurso"]["id"]
    for metodo, rota, corpo in [
        ("patch", f"/resources/{rid}", {"nome": "x"}),
        ("delete", f"/resources/{rid}", None),
        ("put", f"/availability/rules?resource_id={rid}", {"janelas": []}),
    ]:
        chamada = getattr(client, metodo)
        resposta = chamada(rota, json=corpo) if corpo is not None else chamada(rota)
        assert resposta.status_code == 403, f"{metodo.upper()} {rota}"
        assert resposta.json()["code"] == "ESCOPO_INSUFICIENTE"


@pytest.fixture()
def bearer_de_atendimento_sem_sessao(org_id):
    """Um token `agk_` de papel atendimento — autenticado, mas sem conversa:
    nenhum titular, porque ninguém provou endereço nenhum."""
    app.dependency_overrides[credencial_atual] = credencial_falsa(
        org_id, "atendimento", ator="agente", nome="Bot sem conversa"
    )
    yield
    app.dependency_overrides.pop(credencial_atual, None)


def test_a_fila_inteira_exige_operacao(client, catalogo, bearer_de_atendimento_sem_sessao):
    """A fila é nome, telefone e janela de todo mundo que espera — a mesma
    classe de dado que já fazia `GET /appointments?date=` exigir operação.

    O isolamento por titular (RF-19) não fechava esta porta sozinho: um bearer
    de papel `atendimento` sem sessão de conversa não tem titular, e a
    filtragem por titular simplesmente não se aplicava a ele.
    """
    resposta = client.get("/waitlist")
    assert resposta.status_code == 403
    assert resposta.json()["code"] == "ESCOPO_INSUFICIENTE"
