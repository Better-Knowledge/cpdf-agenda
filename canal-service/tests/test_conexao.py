"""Etapa 6 — ciclo de vida da instância: criar, apontar webhook, QR, estado.

A parte de driver roda sem banco (transporte HTTP falso); as rotas do canal
usam o Postgres de teste como o resto da suíte.
"""

import json

import httpx
import pytest

from .conftest import integracao

CREDS = {"server_url": "http://evo.local", "instancia": "demo", "apikey": "k"}
WEBHOOK = "http://canal-service:8000/webhooks/canal/evolution?token=segredo"


def _driver_evolution(responder):
    from app.drivers.evolution import DriverEvolution

    return DriverEvolution(http=httpx.Client(transport=httpx.MockTransport(responder)))


def _responder_padrao(chamadas, *, create_status=201, connect_corpo=None):
    def responder(request: httpx.Request) -> httpx.Response:
        chamadas.append(request)
        url = str(request.url)
        if url.endswith("/instance/create"):
            corpo = {"response": {"message": ['This name "demo" is already in use.']}}
            return httpx.Response(create_status, json=corpo if create_status >= 400 else {})
        if "/webhook/set/" in url:
            return httpx.Response(200, json={})
        if "/instance/connect/" in url:
            return httpx.Response(
                200, json=connect_corpo if connect_corpo is not None else {"base64": "data:image/png;base64,QQ=="}
            )
        if "/instance/connectionState/" in url:
            return httpx.Response(200, json={"instance": {"state": "open"}})
        raise AssertionError(f"chamada inesperada: {url}")

    return responder


def test_conectar_cria_instancia_aponta_webhook_e_devolve_qr():
    chamadas: list[httpx.Request] = []
    driver = _driver_evolution(_responder_padrao(chamadas))

    estado = driver.conectar(CREDS, WEBHOOK)

    assert estado.estado == "aguardando_qr"
    assert estado.qr_base64.startswith("data:image/png")
    # o webhook aponta para o canal, só com o evento de mensagem
    (webhook_req,) = [r for r in chamadas if "/webhook/set/demo" in str(r.url)]
    corpo = json.loads(webhook_req.content)["webhook"]
    assert corpo["url"] == WEBHOOK
    assert corpo["events"] == ["MESSAGES_UPSERT"]
    assert webhook_req.headers["apikey"] == "k"


def test_conectar_tolera_instancia_ja_existente():
    chamadas: list[httpx.Request] = []
    driver = _driver_evolution(_responder_padrao(chamadas, create_status=403))
    assert driver.conectar(CREDS, WEBHOOK).estado == "aguardando_qr"


def test_conectar_ja_pareada_devolve_estado_conectado():
    chamadas: list[httpx.Request] = []
    driver = _driver_evolution(
        _responder_padrao(chamadas, connect_corpo={"instance": {"state": "open"}})
    )
    estado = driver.conectar(CREDS, WEBHOOK)
    assert estado.estado == "conectado"
    assert estado.qr_base64 is None


@pytest.mark.parametrize(
    ("cru", "normalizado"),
    [("open", "conectado"), ("connecting", "aguardando_qr"), ("close", "desconectado")],
)
def test_estado_conexao_normaliza_entre_drivers(cru, normalizado):
    def responder(request):
        return httpx.Response(200, json={"instance": {"state": cru}})

    assert _driver_evolution(responder).estado_conexao(CREDS).estado == normalizado


# ── Rotas do canal (integração) ──────────────────────────────────────────────


@integracao
def test_config_e_legivel_sem_vazar_credenciais(client, canal_configurado):
    canal_configurado("evolution")
    corpo = client.get("/canal/config").json()
    assert corpo["configurado"] is True
    assert corpo["driver"] == "evolution"
    assert "apikey" not in json.dumps(corpo)  # write-only de verdade
    assert "/webhooks/canal/evolution?token=" in corpo["webhook_url"]


@integracao
def test_config_inexistente_nao_e_erro(client):
    assert client.get("/canal/config").json() == {
        "configurado": False,
        "driver": None,
        "numero": None,
        "instancia": None,
        "ativo": False,
        "webhook_url": None,
    }


@integracao
def test_conectar_pela_rota_devolve_qr(client, canal_configurado, monkeypatch):
    canal_configurado("evolution")

    import app.routers.canal as canal_router
    from app.drivers.evolution import DriverEvolution

    class DriverStub(DriverEvolution):
        def conectar(self, credenciais, webhook_url):
            from app.drivers.base import EstadoConexao

            # a instância vem da config (fonte de verdade), e o webhook leva o token
            assert credenciais["instancia"]
            assert "?token=" in webhook_url
            return EstadoConexao(estado="aguardando_qr", qr_base64="data:image/png;base64,QQ==")

    monkeypatch.setattr(canal_router, "obter_driver", lambda nome, http=None: DriverStub())
    corpo = client.post("/canal/conectar").json()
    assert corpo["estado"] == "aguardando_qr"
    assert corpo["qr_base64"].startswith("data:image/png")


@integracao
def test_driver_sem_suporte_a_conexao_explica_o_caminho(client, canal_configurado):
    canal_configurado("zapi")  # conexão do Z-API é no painel do fornecedor
    resposta = client.post("/canal/conectar")
    assert resposta.status_code == 502
    corpo = resposta.json()
    assert corpo["code"] == "FALHA_NO_DRIVER"
    assert "painel" in corpo["hint"]


@integracao
def test_optouts_listam_e_removem(client, canal_configurado, org_id):
    canal_configurado("evolution")
    from app.db import SessionLocal, sessao_org
    from app.models import ChannelOptout

    with SessionLocal() as db:
        sessao_org(db, org_id)
        db.add(ChannelOptout(org_id=org_id, telefone="+5511911112222", origem="palavra_chave"))
        db.commit()

    lista = client.get("/canal/optouts").json()
    assert [o["telefone"] for o in lista] == ["+5511911112222"]

    assert client.delete("/canal/optouts/+5511911112222").json()["removido"] is True
    assert client.get("/canal/optouts").json() == []
    # idempotente
    assert client.delete("/canal/optouts/+5511911112222").json()["removido"] is False


@integracao
def test_webhook_url_sai_redigida_por_padrao(client, canal_configurado):
    """O token na webhook_url autentica o inbound: quem o obtém forja mensagem
    como qualquer cliente da organização. Ele não pode sair em toda leitura de
    configuração — só quando alguém pede."""
    canal_configurado("evolution")

    lida = client.get("/canal/config").json()
    assert "token=***" in lida["webhook_url"]

    revelada = client.post("/canal/webhook-url/revelar").json()
    assert "token=***" not in revelada["webhook_url"]
    assert len(revelada["webhook_url"].split("token=")[1].split("&")[0]) > 20
