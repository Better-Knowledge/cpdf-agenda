"""Aceite do RF-10: a MESMA suíte passa nos dois drivers — trocar é configuração."""

import pytest

from .conftest import integracao

pytestmark = integracao

TELEFONE = "+5511977776666"


@pytest.mark.parametrize("driver", ["evolution", "zapi"])
def test_fluxo_completo_por_driver(client, canal_configurado, instancia, driver):
    transporte = canal_configurado(driver)

    resposta = client.post(
        "/canal/enviar",
        json={
            "destinatario": TELEFONE,
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
    else:
        assert f"/instances/{instancia}/token/t/send-text" in url
        assert requisicao.headers["Client-Token"] == "ct"

    historico = client.get("/canal/mensagens", params={"telefone": TELEFONE}).json()
    assert historico[0]["driver"] == driver
    assert historico[0]["status"] == "enviada"
