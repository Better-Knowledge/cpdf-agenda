# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""RF-19 — o canal cunha a autoridade do agente, porque é aqui que o endereço
do cliente deixa de ser afirmação e vira evidência.

O par deste arquivo é `agenda-service/tests/test_atendimento_isolado.py`, que
valida o mesmo formato do outro lado. Os dois serviços são deployables
separados, sem biblioteca comum: se o formato divergir, é aqui que se vê.
"""

import base64
import hashlib
import hmac
import json
import uuid

from .conftest import integracao

DOMINIO = b"cpdf.sessao-atendimento.v1"
SEGREDO = b"segredo-de-sessao-teste"


def _abrir(token: str) -> dict:
    """Verifica e abre o token do jeito que o agenda-service faz — escrito à
    mão de propósito, para o teste falhar se o formato mudar de um lado só."""
    assert token.startswith("ats_")
    payload, assinatura = token.removeprefix("ats_").split(".")
    corpo = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    esperada = hmac.new(SEGREDO, DOMINIO + b"|" + corpo, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(assinatura, esperada), "assinatura fora do contrato"
    return json.loads(corpo)


def test_formato_do_token_e_o_que_a_agenda_espera():
    from app.sessao_atendimento import emitir

    org = uuid.uuid4()
    claims = _abrir(emitir(org, "+5511955554444"))

    assert set(claims) == {"org", "tit", "esc", "jti", "exp"}
    assert claims["org"] == str(org)
    assert claims["tit"] == "+5511955554444"
    assert claims["esc"] == ["agenda:read", "agenda:write"]


def test_o_canal_nunca_cunha_mais_do_que_atendimento():
    """O canal não tem como conceder cancelamento ou administração: não há
    parâmetro para isso. A agenda ainda apara no teto, mas a primeira porta
    fechada é esta."""
    from app.sessao_atendimento import ESCOPOS_ATENDIMENTO

    assert set(ESCOPOS_ATENDIMENTO) == {"agenda:read", "agenda:write"}


def test_titular_sai_normalizado():
    from app.sessao_atendimento import emitir, normalizar

    assert normalizar("+55 11 95555-4444") == "+5511955554444"
    assert _abrir(emitir(uuid.uuid4(), "+55 11 95555-4444"))["tit"] == "+5511955554444"
    assert _abrir(emitir(uuid.uuid4(), "TG: 987"))["tit"] == "tg:987"


def test_cada_token_e_unico():
    """`jti` distinto por mensagem: dois inbounds do mesmo cliente não
    produzem o mesmo bearer, e um token vazado não se confunde com outro."""
    from app.sessao_atendimento import emitir

    org = uuid.uuid4()
    a, b = emitir(org, "+5511955554444"), emitir(org, "+5511955554444")
    assert _abrir(a)["jti"] != _abrir(b)["jti"]


@integracao
def test_inbound_valido_leva_o_token_ao_orquestrador(
    client, canal_configurado, instancia, org_id, monkeypatch
):
    from .test_encaminha_orquestrador import _capturar_envios, _payload_evolution, _token

    canal_configurado("evolution")
    from app.config import settings

    monkeypatch.setattr(settings(), "orquestrador_url", "http://agente:8000/inbound")
    envios = _capturar_envios(monkeypatch)

    client.post(
        f"/webhooks/canal/evolution?token={_token(client)}", json=_payload_evolution(instancia)
    )
    ((_, kwargs),) = envios
    claims = _abrir(kwargs["json"]["sessao"])
    assert claims["org"] == str(org_id)
    assert claims["tit"] == "+5511955554444"


@integracao
def test_inbound_com_token_errado_nao_cunha_nada(client, canal_configurado, instancia, monkeypatch):
    """A ordem importa: o token só existe DEPOIS do compare_digest. Um inbound
    forjado não pode sair daqui com autoridade para falar por ninguém."""
    from .test_encaminha_orquestrador import _capturar_envios, _payload_evolution

    canal_configurado("evolution")
    from app.config import settings

    monkeypatch.setattr(settings(), "orquestrador_url", "http://agente:8000/inbound")
    envios = _capturar_envios(monkeypatch)

    resposta = client.post(
        "/webhooks/canal/evolution?token=token-forjado", json=_payload_evolution(instancia)
    )
    assert resposta.json()["resultado"] == "token_invalido"
    assert envios == []
