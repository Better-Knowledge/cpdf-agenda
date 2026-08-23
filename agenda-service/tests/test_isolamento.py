"""Os furos que existiam antes da separação de papéis.

Cada teste aqui corresponde a um vazamento real que uma credencial de
atendimento explorava. Eles falham se alguém afrouxar os escopos de volta.
"""

import uuid

import pytest

from app.auth import credencial_atual
from app.main import app

from .conftest import credencial_falsa, integracao

pytestmark = integracao


@pytest.fixture()
def como_atendimento(org_id):
    """Roda as chamadas como um agente de canal: read + write, nada mais."""
    app.dependency_overrides[credencial_atual] = credencial_falsa(
        org_id, "atendimento", ator="agente", nome="Bot do canal"
    )
    yield
    app.dependency_overrides.pop(credencial_atual, None)


def _erro(resposta) -> str:
    return resposta.json().get("code", "")


# ── O vazamento crítico: o segredo do webhook ────────────────────────────────


def test_atendimento_nao_alcanca_o_canal(client, catalogo, como_atendimento):
    """`GET /canal/config` devolve a webhook_url. O token nela autentica o
    inbound: quem o obtém forja mensagem como QUALQUER cliente da organização
    — o que anularia todo o isolamento construído por cima."""
    for metodo, rota in [
        ("get", "/canal/config"),
        ("get", "/canal/status"),
        ("get", "/canal/templates"),
        ("get", "/canal/optouts"),
    ]:
        resposta = getattr(client, metodo)(rota)
        assert resposta.status_code == 403, f"{metodo.upper()} {rota} deveria ser 403"
        assert _erro(resposta) == "ESCOPO_INSUFICIENTE"


def test_atendimento_nao_configura_canal(client, catalogo, como_atendimento):
    resposta = client.post(
        "/canal/config",
        json={
            "driver": "telegram",
            "numero": "@bot",
            "instancia": "x",
            "credenciais": {"bot_token": "123:ABC"},
        },
    )
    assert resposta.status_code == 403


# ── Replay de idempotência atravessando titulares ────────────────────────────


def test_replay_de_idempotency_de_outro_titular_nao_vaza_corpo(client, catalogo, org_id):
    """`idem.buscar` roda ANTES das guardas de propriedade nos handlers. Sem o
    titular na chave, repetir a Idempotency-Key de outra pessoa devolveria o
    corpo dela — nome, contato e horário — sem passar por checagem nenhuma."""
    chave = str(uuid.uuid4())
    corpo = {
        "service_id": catalogo["servico"]["id"],
        "resource_id": catalogo["recurso"]["id"],
        "inicio": "2027-09-08T10:00:00-03:00",
        "cliente_nome": "Ana Original",
        "cliente_telefone": "+5511900001111",
    }

    def como(titular: str | None):
        app.dependency_overrides[credencial_atual] = credencial_falsa(
            org_id, "atendimento", ator="agente", titular=titular
        )

    como("+5511900001111")
    primeira = client.post("/appointments", json=corpo, headers={"Idempotency-Key": chave})
    assert primeira.status_code == 201, primeira.text
    assert primeira.json()["cliente_nome"] == "Ana Original"

    # outro titular, MESMA chave, mesmo endpoint
    como("+5511900002222")
    segunda = client.post(
        "/appointments",
        json={**corpo, "cliente_nome": "Bia", "cliente_telefone": "+5511900002222",
              "inicio": "2027-09-08T14:00:00-03:00"},
        headers={"Idempotency-Key": chave},
    )
    app.dependency_overrides.pop(credencial_atual, None)

    assert segunda.status_code == 201, segunda.text
    assert segunda.json()["cliente_nome"] == "Bia", "vazou o corpo do outro titular"
    assert segunda.json()["id"] != primeira.json()["id"]


# ── Dados de terceiros exigem escopo de operação ─────────────────────────────


def test_atendimento_nao_ve_a_agenda_do_dia(client, catalogo, como_atendimento):
    """A `narrativa` de /agenda/day nomeia todos os clientes do dia, pronta
    para um LLM repetir em voz alta."""
    assert client.get("/agenda/day?date=2027-09-08").status_code == 403
    assert client.get("/appointments?date=2027-09-08").status_code == 403


def test_atendimento_nao_le_bloqueios(client, catalogo, como_atendimento):
    """O `motivo` do bloqueio é nota interna: 'cirurgia', 'férias em Ilhabela'."""
    assert client.get("/availability/blocks").status_code == 403


def test_atendimento_nao_marca_falta(client, catalogo, como_atendimento):
    resposta = client.post(f"/appointments/{uuid.uuid4()}/no-show")
    assert resposta.status_code == 403
    assert _erro(resposta) == "ESCOPO_INSUFICIENTE"


def test_atendimento_nao_cancela(client, catalogo, como_atendimento):
    """Aceite do PRD §14.4, agora executável."""
    resposta = client.post(f"/appointments/{uuid.uuid4()}/cancel", json={"motivo": "x"})
    assert resposta.status_code == 403


def test_atendimento_nao_cancela_serie_alheia(client, catalogo, como_atendimento):
    resposta = client.post(
        f"/appointments/recorrentes/{uuid.uuid4()}/cancel", json={"motivo": "x"}
    )
    assert resposta.status_code == 403


# ── Catálogo e grade são administrativos ─────────────────────────────────────


def test_atendimento_nao_cria_servico(client, catalogo, como_atendimento):
    resposta = client.post("/services", json={"nome": "Pirata", "duracao_min": 30})
    assert resposta.status_code == 403
    assert _erro(resposta) == "ESCOPO_INSUFICIENTE"
    assert "administrativo" in resposta.json()["hint"]


def test_atendimento_ainda_faz_o_que_e_dele(client, catalogo, como_atendimento):
    """A contraprova: apertar não pode ter quebrado o atendimento."""
    assert client.get("/services").status_code == 200
    assert client.get(
        "/slots",
        params={
            "service_id": catalogo["servico"]["id"],
            "from": "2027-09-08T09:00:00-03:00",
            "to": "2027-09-08T18:00:00-03:00",
        },
    ).status_code == 200
    criado = client.post(
        "/appointments",
        json={
            "service_id": catalogo["servico"]["id"],
            "resource_id": catalogo["recurso"]["id"],
            "inicio": "2027-09-09T10:00:00-03:00",
            "cliente_nome": "Cliente",
            "cliente_telefone": "+5511900003333",
        },
    )
    assert criado.status_code == 201, criado.text
    assert client.post(f"/appointments/{criado.json()['id']}/confirm").status_code == 200
