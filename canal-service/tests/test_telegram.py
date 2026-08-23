"""Driver Telegram — o canal de demonstração da aula.

Sem QR, sem chip, sem número pessoal em risco: o que muda em relação ao
WhatsApp é o endereço do cliente (`tg:<chat_id>`) e o fato de o update não
dizer de qual bot veio — a instância vem da URL do webhook.
"""

import json
import uuid

import httpx
import pytest

from .conftest import integracao

CREDS = {"bot_token": "123456:ABC", "webhook_secret": "segredo-do-webhook"}
WEBHOOK = "https://cpdf.exemplo/webhooks/canal/telegram?token=segredo-do-webhook&instancia=aula"


def _driver(responder):
    from app.drivers.telegram import DriverTelegram

    return DriverTelegram(http=httpx.Client(transport=httpx.MockTransport(responder)))


def _update(texto: str = "confirmo", chat_id: int = 987654321, **extra):
    mensagem = {
        "message_id": 42,
        "from": {"id": chat_id, "is_bot": False, "first_name": "Bia"},
        "chat": {"id": chat_id, "type": "private"},
        "date": 1787000000,
        "text": texto,
        **extra,
    }
    return {"update_id": 100, "message": mensagem}


# ── Driver puro (sem banco) ──────────────────────────────────────────────────


def test_inbound_vira_endereco_com_prefixo():
    inbound = _driver(lambda r: httpx.Response(200, json={})).normalizar_inbound(_update())
    assert inbound is not None
    assert inbound.telefone == "tg:987654321"  # nunca colide com E.164
    assert inbound.texto == "confirmo"
    # message_id do Telegram é único por CHAT — qualificado para a idempotência
    assert inbound.message_id == "987654321:42"
    assert inbound.instancia == ""  # o update não identifica o bot


@pytest.mark.parametrize(
    "payload",
    [
        {"update_id": 1},  # update sem mensagem
        {"update_id": 1, "message": {"chat": {"id": 1}, "from": {"id": 1, "is_bot": True}, "text": "eco"}},
        {"update_id": 1, "message": {"chat": {"id": 1}, "from": {"id": 1}, "photo": [{}]}},  # sem texto
        {"update_id": 1, "callback_query": {"id": "x"}},
    ],
)
def test_eventos_sem_texto_util_sao_ignorados(payload):
    assert _driver(lambda r: httpx.Response(200, json={})).normalizar_inbound(payload) is None


def test_envio_tira_o_prefixo_e_qualifica_o_id():
    chamadas = []

    def responder(request):
        chamadas.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 77}})

    resultado = _driver(responder).enviar_texto(CREDS, "tg:555", "Oi!")
    assert json.loads(chamadas[0].content)["chat_id"] == "555"
    assert "/bot123456:ABC/sendMessage" in str(chamadas[0].url)
    assert resultado.driver_message_id == "555:77"


def test_conectar_registra_webhook_com_segredo():
    chamadas = []

    def responder(request):
        chamadas.append(request)
        if str(request.url).endswith("/getMe"):
            return httpx.Response(200, json={"ok": True, "result": {"username": "agenda_bot"}})
        return httpx.Response(200, json={"ok": True, "result": True})

    estado = _driver(responder).conectar(CREDS, WEBHOOK)
    assert estado.estado == "conectado"  # bot não precisa de pareamento
    assert estado.qr_base64 is None
    assert "@agenda_bot" in estado.detalhe

    (set_webhook,) = [c for c in chamadas if str(c.url).endswith("/setWebhook")]
    corpo = json.loads(set_webhook.content)
    assert corpo["url"] == WEBHOOK
    assert corpo["secret_token"] == "segredo-do-webhook"
    assert corpo["allowed_updates"] == ["message"]


def test_token_errado_nao_e_retryable():
    from app.drivers.base import ErroDriver

    def responder(request):
        return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

    with pytest.raises(ErroDriver) as e:
        _driver(responder).enviar_texto(CREDS, "tg:1", "oi")
    assert e.value.retryable is False  # repetir com token errado não ajuda


def test_estado_sem_webhook_e_desconectado():
    def responder(request):
        return httpx.Response(200, json={"ok": True, "result": {"url": ""}})

    estado = _driver(responder).estado_conexao(CREDS)
    assert estado.estado == "desconectado"
    assert "Conectar" in estado.detalhe


# ── Integração com o canal ───────────────────────────────────────────────────


@integracao
def test_bot_nao_exige_confirmacao_de_numero_dedicado(client):
    """A regra existe contra o ban de WhatsApp levando o número pessoal junto.
    Um bot já é identidade separada — exigir a confirmação seria burocracia."""
    resposta = client.post(
        "/canal/config",
        json={
            "driver": "telegram",
            "numero": "@agenda_bot",
            "instancia": f"tg-{uuid.uuid4().hex[:8]}",
            "credenciais": {"bot_token": "123456:ABC"},
            # sem confirmo_numero_dedicado
        },
    )
    assert resposta.status_code == 201, resposta.text
    # e o webhook aponta para a URL PÚBLICA (o Telegram é serviço de nuvem)
    assert resposta.json()["webhook_url"].startswith("https://canal.exemplo.test")


@integracao
def test_whatsapp_continua_exigindo_numero_dedicado(client):
    resposta = client.post(
        "/canal/config",
        json={
            "driver": "evolution",
            "numero": "+5511900000000",
            "instancia": f"wa-{uuid.uuid4().hex[:8]}",
            "credenciais": {"server_url": "http://x", "apikey": "k"},
        },
    )
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "NUMERO_PESSOAL_RECUSADO"


@integracao
def test_inbound_roteia_pela_instancia_da_url(client, canal_configurado, instancia):
    """O update do Telegram não diz de qual bot veio: a instância vem da URL,
    que é única por organização. Quem autentica continua sendo o token."""
    transporte = canal_configurado("telegram")
    url = transporte.webhook_url
    assert f"instancia={instancia}" in url

    resposta = client.post(url, json=_update("confirmo"))
    assert resposta.json()["resultado"] == "registrado"

    historico = client.get("/canal/mensagens", params={"telefone": "tg:987654321"}).json()
    assert historico[0]["direcao"] == "entrada"
    assert historico[0]["corpo_renderizado"] == "confirmo"


@integracao
def test_segredo_pode_vir_no_header_do_telegram(client, canal_configurado, instancia):
    transporte = canal_configurado("telegram")
    token = transporte.webhook_url.split("token=")[1].split("&")[0]

    # sem token na URL, mas com o header que o Telegram envia
    resposta = client.post(
        f"/webhooks/canal/telegram?instancia={instancia}",
        json=_update("confirmo", chat_id=111222),
        headers={"X-Telegram-Bot-Api-Secret-Token": token},
    )
    assert resposta.json()["resultado"] == "registrado"


@integracao
def test_inbound_forjado_sem_segredo_nao_tem_efeito(client, canal_configurado, instancia):
    canal_configurado("telegram")
    resposta = client.post(
        f"/webhooks/canal/telegram?instancia={instancia}&token=chutado",
        json=_update("SAIR", chat_id=333444),
    )
    assert resposta.json()["resultado"] == "token_invalido"
    # nada aconteceu: nem mensagem registrada, nem opt-out gravado
    assert client.get("/canal/mensagens", params={"telefone": "tg:333444"}).json() == []
    assert client.get("/canal/optouts").json() == []


@integracao
def test_optout_funciona_igual_no_telegram(client, canal_configurado, instancia):
    """"SAIR" é regra determinística, antes de qualquer LLM — vale em todo canal."""
    transporte = canal_configurado("telegram")
    resposta = client.post(transporte.webhook_url, json=_update("SAIR", chat_id=444555))
    assert resposta.json()["resultado"] == "optout_registrado"

    assert [o["telefone"] for o in client.get("/canal/optouts").json()] == ["tg:444555"]

    # e o envio ativo passa a ser recusado
    recusado = client.post(
        "/canal/enviar",
        json={
            "destinatario": "tg:444555",
            "tipo": "template",
            "template_nome": "lembrete_24h",
            "variaveis": {"nome": "Bia", "servico": "corte", "data_hora": "sexta, 10h"},
        },
    )
    assert recusado.status_code == 403
    assert recusado.json()["code"] == "OPTOUT_ATIVO"
