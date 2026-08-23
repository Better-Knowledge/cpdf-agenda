# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Inbound: normalização, idempotência por (driver, message_id) e opt-out por regra."""

from .conftest import integracao

pytestmark = integracao

TELEFONE = "5511966665555"


def _payload_evolution(instancia: str, texto: str, message_id: str = "MSG-1") -> dict:
    return {
        "event": "messages.upsert",
        "instance": instancia,
        "data": {
            "key": {"remoteJid": f"{TELEFONE}@s.whatsapp.net", "fromMe": False, "id": message_id},
            "message": {"conversation": texto},
            "messageTimestamp": 1756200000,
        },
    }


def test_inbound_registra_e_abre_sessao(client, canal_configurado, instancia):
    transporte = canal_configurado()
    resposta = client.post(
        transporte.webhook_url, json=_payload_evolution(instancia, "quero marcar")
    )
    assert resposta.status_code == 200
    assert resposta.json()["resultado"] == "registrado"

    # com a sessão aberta, resposta livre (tipo=sessao) passa a ser permitida
    envio = client.post(
        "/canal/enviar",
        json={"destinatario": f"+{TELEFONE}", "tipo": "sessao", "texto": "Claro! Que dia?"},
    )
    assert envio.status_code == 200, envio.text


def test_replay_do_webhook_nao_duplica(client, canal_configurado, instancia):
    transporte = canal_configurado()
    payload = _payload_evolution(instancia, "oi", message_id="MSG-REPLAY")
    assert client.post(transporte.webhook_url, json=payload).json()["resultado"] == "registrado"
    assert (
        client.post(transporte.webhook_url, json=payload).json()["resultado"]
        == "replay_ignorado"
    )


def test_sair_registra_optout_antes_de_qualquer_llm(client, canal_configurado, instancia):
    transporte = canal_configurado()
    resposta = client.post(
        transporte.webhook_url,
        json=_payload_evolution(instancia, "SAIR", message_id="MSG-SAIR"),
    )
    assert resposta.json()["resultado"] == "optout_registrado"

    # confirmação de saída foi enviada pelo driver (sessão aberta pelo cliente)
    assert any("sendText" in str(r.url) for r in transporte.requisicoes)

    # e o envio ativo seguinte é bloqueado
    envio = client.post(
        "/canal/enviar",
        json={
            "destinatario": f"+{TELEFONE}",
            "tipo": "template",
            "template_nome": "lembrete_24h",
            "variaveis": {"nome": "X", "servico": "y", "data_hora": "z"},
        },
    )
    assert envio.status_code == 403
    assert envio.json()["code"] == "OPTOUT_ATIVO"


def test_instancia_desconhecida_e_ignorada_com_200(client, canal_configurado, instancia):
    transporte = canal_configurado()
    payload = _payload_evolution(instancia, "oi", message_id="MSG-X")
    payload["instance"] = "instancia-fantasma"
    resposta = client.post(transporte.webhook_url, json=payload)
    assert resposta.status_code == 200
    assert resposta.json()["resultado"] == "instancia_desconhecida"


def test_webhook_sem_token_valido_e_descartado(client, canal_configurado, instancia):
    """Segredo verificado (PRD §9): payload forjado não produz NENHUM efeito."""
    canal_configurado()
    payload = _payload_evolution(instancia, "SAIR", message_id="MSG-FORJADA")

    sem_token = client.post("/webhooks/canal/evolution", json=payload)
    assert sem_token.status_code == 200  # 200 sem processar: sem tempestade de retry
    assert sem_token.json()["resultado"] == "token_invalido"

    token_errado = client.post("/webhooks/canal/evolution?token=chutado", json=payload)
    assert token_errado.json()["resultado"] == "token_invalido"

    # o "SAIR" forjado NÃO registrou opt-out: envio ativo continua permitido
    envio = client.post(
        "/canal/enviar",
        json={
            "destinatario": f"+{TELEFONE}",
            "tipo": "template",
            "template_nome": "lembrete_24h",
            "variaveis": {"nome": "X", "servico": "y", "data_hora": "z"},
        },
    )
    assert envio.status_code == 200
