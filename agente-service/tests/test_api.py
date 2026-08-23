"""A porta do agente: só o canal entra, e falha nunca vira 5xx."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

CHAVE = {"X-Service-Key": "chave-do-agente-teste"}
CORPO = {"org_id": str(uuid.uuid4()), "telefone": "+5511955554444", "texto": "confirmo"}


@pytest.fixture()
def client():
    return TestClient(app)


def test_inbound_exige_credencial(client):
    assert client.post("/inbound", json=CORPO).status_code == 401
    assert client.post("/inbound", json=CORPO, headers={"X-Service-Key": "errada"}).status_code == 401


def test_inbound_trata_e_responde(client, agenda_falsa):
    from .conftest import COMPROMISSO

    agenda_falsa.compromisso = COMPROMISSO
    corpo = client.post("/inbound", json=CORPO, headers=CHAVE).json()
    assert corpo["intencao"] == "confirmar"
    assert corpo["acao"] == "confirmado"


def test_falha_interna_nao_vira_5xx(client, monkeypatch):
    """O canal já registrou a mensagem: derrubar o webhook com 500 só geraria
    tempestade de retry."""
    import app.main as main

    def explodir(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(main.fluxo, "tratar", explodir)
    resposta = client.post("/inbound", json=CORPO, headers=CHAVE)
    assert resposta.status_code == 200
    assert resposta.json()["acao"] == "erro_interno_logado"


def test_health_diz_se_tem_llm(client):
    assert client.get("/health").json()["classificacao"] == "somente_regras"
