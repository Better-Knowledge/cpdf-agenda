"""RF-16 — importação one-way do Calendly.

O webhook é público: quem autentica é a assinatura, e é ela também que diz de
qual organização é o evento. Os testes cobrem esse par (assinatura = auth =
roteamento) e as três recusas silenciosas que precisam responder 200, porque
um 4xx faria o Calendly reenviar para sempre.
"""

import hashlib
import hmac
import json
from datetime import datetime, timedelta

import pytest

from .conftest import integracao

pytestmark = integracao

@pytest.fixture()
def CHAVE(org_id) -> str:
    """Uma chave por organização — na vida real elas são aleatórias, e duas
    integrações com a mesma chave tornam o evento inatribuível (o produto
    descarta, de propósito)."""
    return f"chave-de-assinatura-{org_id}"


def _dia_util(daqui_a: int = 4, hora: int = 15) -> datetime:
    from app.tempo import TZ

    dia = (datetime.now(TZ) + timedelta(days=daqui_a)).replace(
        hour=hora, minute=0, second=0, microsecond=0
    )
    while dia.weekday() > 4:
        dia += timedelta(days=1)
    return dia


def _assinar(corpo: bytes, chave: str, quando: datetime | None = None) -> str:
    t = int((quando or datetime.now()).timestamp())
    v1 = hmac.new(chave.encode(), f"{t}.".encode() + corpo, hashlib.sha256).hexdigest()
    return f"t={t},v1={v1}"


def _evento(inicio: datetime, *, tipo="invitee.created", uri="https://api.calendly.com/i/abc",
            nome="Carla Dias", telefone: str | None = "+5511955554444") -> bytes:
    payload = {
        "uri": uri,
        "name": nome,
        "email": "carla@example.com",
        "scheduled_event": {
            "start_time": inicio.isoformat(),
            "end_time": (inicio + timedelta(minutes=45)).isoformat(),
        },
    }
    if telefone:
        payload["text_reminder_number"] = telefone
    return json.dumps({"event": tipo, "payload": payload}).encode()


def _configurar(client, catalogo, CHAVE, **extra) -> dict:
    resposta = client.put(
        "/integracoes/calendly",
        json={
            "service_id": catalogo["servico"]["id"],
            "resource_id": catalogo["recurso"]["id"],
            "chave_assinatura": CHAVE,
            **extra,
        },
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _mandar(client, corpo: bytes, CHAVE: str, assinatura: str | None = None):
    return client.post(
        "/webhooks/calendly",
        content=corpo,
        headers={
            "Calendly-Webhook-Signature": assinatura or _assinar(corpo, CHAVE),
            "Content-Type": "application/json",
            "X-Org-Id": "",
        },
    )


def test_a_configuracao_nunca_devolve_a_chave(client, catalogo, CHAVE):
    corpo = _configurar(client, catalogo, CHAVE)
    assert CHAVE not in json.dumps(corpo)
    assert corpo["webhook_url"].endswith("/webhooks/calendly")
    assert corpo["cria_lembretes"] is False  # o Calendly já manda os dele


def test_sem_configurar_a_integracao_e_nula(client, catalogo):
    assert client.get("/integracoes/calendly").json() is None


def test_evento_assinado_vira_compromisso(client, catalogo, CHAVE):
    _configurar(client, catalogo, CHAVE)
    inicio = _dia_util()
    resposta = _mandar(client, _evento(inicio), CHAVE)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == {"importado": True, "motivo": "compromisso criado"}

    (ap,) = [
        a
        for a in client.get("/appointments", params={"date": inicio.date().isoformat()}).json()
        if a["cliente_nome"] == "Carla Dias"
    ]
    assert ap["origem"] == "calendly"
    assert ap["cliente_telefone"] == "+5511955554444"


def test_reenvio_do_mesmo_evento_nao_duplica(client, catalogo, CHAVE):
    _configurar(client, catalogo, CHAVE)
    corpo = _evento(_dia_util(daqui_a=5))
    assert _mandar(client, corpo, CHAVE).json()["importado"] is True
    repetido = _mandar(client, corpo, CHAVE)
    assert repetido.status_code == 200
    assert repetido.json() == {"importado": False, "motivo": "evento já importado"}


def test_assinatura_errada_nao_importa_nada(client, catalogo, CHAVE):
    _configurar(client, catalogo, CHAVE)
    corpo = _evento(_dia_util(daqui_a=6))
    recusado = _mandar(client, corpo, CHAVE, assinatura=_assinar(corpo, chave="chave-errada-de-teste"))
    assert recusado.status_code == 401
    assert recusado.json()["code"] == "ASSINATURA_INVALIDA"


def test_assinatura_velha_nao_vale(client, catalogo, CHAVE):
    """Sem janela de tolerância, uma assinatura capturada valeria para sempre."""
    _configurar(client, catalogo, CHAVE)
    corpo = _evento(_dia_util(daqui_a=6))
    antiga = _assinar(corpo, CHAVE, quando=datetime.now() - timedelta(hours=2))
    assert _mandar(client, corpo, CHAVE, assinatura=antiga).status_code == 401


def test_cancelamento_no_calendly_reflete_aqui(client, catalogo, CHAVE):
    _configurar(client, catalogo, CHAVE)
    inicio = _dia_util(daqui_a=7)
    uri = "https://api.calendly.com/i/para-cancelar"
    _mandar(client, _evento(inicio, uri=uri), CHAVE)

    resposta = _mandar(client, _evento(inicio, tipo="invitee.canceled", uri=uri), CHAVE)
    assert resposta.json() == {"importado": True, "motivo": "compromisso cancelado"}
    (ap,) = [
        a
        for a in client.get("/appointments", params={"date": inicio.date().isoformat()}).json()
        if a["cliente_nome"] == "Carla Dias"
    ]
    assert ap["status"] == "cancelado"


def test_conflito_de_horario_responde_200_e_avisa(client, catalogo, CHAVE):
    """O Calendly já confirmou com o cliente: recusar com 4xx só faria ele
    reenviar. O horário ocupado vira aviso, não erro de transporte."""
    _configurar(client, catalogo, CHAVE)
    inicio = _dia_util(daqui_a=8)
    assert client.post(
        "/appointments",
        json={
            "service_id": catalogo["servico"]["id"],
            "resource_id": catalogo["recurso"]["id"],
            "inicio": inicio.isoformat(),
            "cliente_nome": "Já marcado aqui",
            "cliente_telefone": "+5511900000000",
        },
    ).status_code == 201

    resposta = _mandar(client, _evento(inicio, uri="https://api.calendly.com/i/conflito"), CHAVE)
    assert resposta.status_code == 200
    assert resposta.json()["importado"] is False
    assert "ocupado" in resposta.json()["motivo"]


def test_convidado_sem_telefone_ganha_endereco_do_calendly(client, catalogo, CHAVE):
    """Não temos como mandar WhatsApp para quem não deu telefone — o endereço
    diz isso na cara, em vez de inventar um número."""
    _configurar(client, catalogo, CHAVE)
    inicio = _dia_util(daqui_a=9)
    _mandar(
        client,
        _evento(inicio, telefone=None, uri="https://api.calendly.com/i/sem-telefone", nome="Sem Fone"),
        CHAVE,
    )
    (ap,) = [
        a
        for a in client.get("/appointments", params={"date": inicio.date().isoformat()}).json()
        if a["cliente_nome"] == "Sem Fone"
    ]
    assert ap["cliente_telefone"] == "calendly:sem-telefone"


def test_desligar_mantem_o_que_ja_foi_importado(client, catalogo, CHAVE):
    _configurar(client, catalogo, CHAVE)
    inicio = _dia_util(daqui_a=10)
    _mandar(client, _evento(inicio, uri="https://api.calendly.com/i/fica"), CHAVE)

    client.delete("/integracoes/calendly")
    assert client.get("/integracoes/calendly").json()["ativo"] is False
    assert [
        a
        for a in client.get("/appointments", params={"date": inicio.date().isoformat()}).json()
        if a["origem"] == "calendly"
    ]
    # e o webhook para de aceitar
    corpo = _evento(inicio + timedelta(hours=1), uri="https://api.calendly.com/i/depois")
    assert _mandar(client, corpo, CHAVE).status_code == 401
