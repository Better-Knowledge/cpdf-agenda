# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""T-09 — o canal chega à UI por procuração: o agenda-service repassa a
chamada com credencial service-to-service e transporta os erros intactos."""

from .conftest import integracao

pytestmark = integracao


def test_proxy_repassa_sucesso(client, monkeypatch):
    from app import canal_client

    chamadas = []

    def chamar_fake(metodo, rota, *, org_id, corpo=None):
        chamadas.append((metodo, rota, corpo))
        return 200, {"configurado": False, "ativo": False}

    monkeypatch.setattr(canal_client, "chamar", chamar_fake)
    corpo = client.get("/canal/config").json()
    assert corpo["configurado"] is False
    assert chamadas == [("GET", "/canal/config", None)]


def test_erro_do_canal_sobe_intacto(client, monkeypatch):
    from app import canal_client

    def chamar_fake(metodo, rota, *, org_id, corpo=None):
        return 409, {
            "code": "CANAL_NAO_CONFIGURADO",
            "message": "A organização não tem canal de WhatsApp configurado.",
            "hint": "Configure driver, número dedicado e credenciais em POST /canal/config.",
            "retryable": False,
        }

    monkeypatch.setattr(canal_client, "chamar", chamar_fake)
    resposta = client.post("/canal/conectar")
    assert resposta.status_code == 409
    assert resposta.json()["code"] == "CANAL_NAO_CONFIGURADO"
    assert "POST /canal/config" in resposta.json()["hint"]


def test_canal_fora_do_ar_vira_502_retryable(client, monkeypatch):
    from app import canal_client

    def chamar_fake(metodo, rota, *, org_id, corpo=None):
        raise canal_client.CanalIndisponivel("connect timeout")

    monkeypatch.setattr(canal_client, "chamar", chamar_fake)
    resposta = client.get("/canal/status")
    assert resposta.status_code == 502
    corpo = resposta.json()
    assert corpo["code"] == "CANAL_INDISPONIVEL"
    assert corpo["retryable"] is True
