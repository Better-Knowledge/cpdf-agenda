"""Aceite do RF-10: a MESMA suíte passa em todos os drivers — trocar é configuração.

O Telegram entra aqui de propósito: se o mesmo teste passa num canal que nem
usa telefone, a abstração do adapter está honesta.
"""

import json

import pytest

from .conftest import integracao

pytestmark = integracao

# Endereço do cliente NESTE canal: E.164 no WhatsApp, tg:<chat_id> no Telegram
DESTINATARIOS = {
    "evolution": "+5511977776666",
    "zapi": "+5511977776666",
    "telegram": "tg:987654321",
}


@pytest.mark.parametrize("driver", ["evolution", "zapi", "telegram"])
def test_fluxo_completo_por_driver(client, canal_configurado, instancia, driver):
    transporte = canal_configurado(driver)
    destinatario = DESTINATARIOS[driver]

    resposta = client.post(
        "/canal/enviar",
        json={
            "destinatario": destinatario,
            "tipo": "template",
            "template_nome": "lembrete_24h",
            "variaveis": {"nome": "Bia", "servico": "consulta", "data_hora": "sexta, 10h"},
        },
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["status"] == "enviada"

    (requisicao,) = transporte.requisicoes
    url = str(requisicao.url)
    if driver == "evolution":
        assert f"/message/sendText/{instancia}" in url
        assert requisicao.headers["apikey"] == "k"
    elif driver == "zapi":
        assert f"/instances/{instancia}/token/t/send-text" in url
        assert requisicao.headers["Client-Token"] == "ct"
    else:
        assert "/bot123456:ABC-token-de-teste/sendMessage" in url
        # o prefixo tg: é endereço interno do canal — não vaza para a API
        assert json.loads(requisicao.content)["chat_id"] == "987654321"

    historico = client.get("/canal/mensagens", params={"telefone": destinatario}).json()
    assert historico[0]["driver"] == driver
    assert historico[0]["status"] == "enviada"
    # o texto é o template renderizado em todos eles — regra do programa,
    # não da Meta: nenhum driver ganha licença para improvisar mensagem ativa
    assert "Bia" in historico[0]["corpo_renderizado"]
