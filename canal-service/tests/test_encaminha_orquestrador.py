# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""PRD §9.1 — inbound registrado segue ao orquestrador, fora do 2xx ao driver."""

import uuid

from .conftest import integracao

pytestmark = integracao


def _payload_evolution(instancia: str, texto: str = "quero remarcar"):
    return {
        "event": "messages.upsert",
        "instance": instancia,
        "data": {
            "key": {
                "remoteJid": "5511955554444@s.whatsapp.net",
                "fromMe": False,
                "id": f"MSG-{uuid.uuid4().hex[:10]}",
            },
            "message": {"conversation": texto},
            "messageTimestamp": 1787000000,
        },
    }


def _capturar_envios(monkeypatch):
    import httpx

    import app.routers.webhooks as webhooks

    envios = []

    def post_fake(url, **kwargs):
        envios.append((url, kwargs))
        return httpx.Response(200, json={"resultado": "tratado"})

    monkeypatch.setattr(webhooks.httpx, "post", post_fake)
    return envios


def test_inbound_registrado_e_encaminhado(client, canal_configurado, instancia, org_id, monkeypatch):
    canal_configurado("evolution")
    from app.config import settings

    monkeypatch.setattr(settings(), "orquestrador_url", "http://agente:8000/inbound")
    monkeypatch.setattr(settings(), "orquestrador_key", "chave-agente")
    envios = _capturar_envios(monkeypatch)

    resposta = client.post(
        f"/webhooks/canal/evolution?token={_token(client)}", json=_payload_evolution(instancia)
    )
    assert resposta.json()["resultado"] == "registrado"
    assert resposta.json()["encaminhado"] is True

    ((url, kwargs),) = envios
    assert url == "http://agente:8000/inbound"
    assert kwargs["headers"]["X-Service-Key"] == "chave-agente"
    corpo = kwargs["json"]
    assert corpo["org_id"] == str(org_id)
    assert corpo["telefone"] == "+5511955554444"
    assert corpo["texto"] == "quero remarcar"


def test_optout_e_replay_nao_vao_ao_orquestrador(client, canal_configurado, instancia, monkeypatch):
    canal_configurado("evolution")
    from app.config import settings

    monkeypatch.setattr(settings(), "orquestrador_url", "http://agente:8000/inbound")
    envios = _capturar_envios(monkeypatch)

    # opt-out morre no canal, por regra — nunca chega ao LLM/agente
    optout = client.post(f"/webhooks/canal/evolution?token={_token(client)}",
                         json=_payload_evolution(instancia, "SAIR"))
    assert optout.json()["resultado"] == "optout_registrado"

    # replay da mesma mensagem: registrado uma vez, encaminhado uma vez
    payload = _payload_evolution(instancia)
    primeira = client.post(f"/webhooks/canal/evolution?token={_token(client)}", json=payload)
    replay = client.post(f"/webhooks/canal/evolution?token={_token(client)}", json=payload)
    assert primeira.json()["resultado"] == "registrado"
    assert replay.json()["resultado"] == "replay_ignorado"
    assert len(envios) == 1


def _token(client) -> str:
    """O segredo sai redigido nas leituras — pedir por ele é explícito."""
    corpo = client.post("/canal/webhook-url/revelar").json()
    return corpo["webhook_url"].split("token=")[1].split("&")[0]
