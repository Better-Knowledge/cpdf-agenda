"""RF-10 — Template-first e opt-out no envio ativo."""

from .conftest import integracao

pytestmark = integracao

TELEFONE = "+5511988887777"


def test_mensagem_ativa_recusa_tipo_sessao(client, canal_configurado):
    canal_configurado()
    resposta = client.post(
        "/canal/enviar",
        json={"destinatario": TELEFONE, "tipo": "sessao", "texto": "oi, lembrete do horário!"},
    )
    assert resposta.status_code == 409
    assert resposta.json()["code"] == "MENSAGEM_ATIVA_EXIGE_TEMPLATE"


def test_template_renderiza_e_envia(client, canal_configurado):
    transporte = canal_configurado()
    resposta = client.post(
        "/canal/enviar",
        json={
            "destinatario": TELEFONE,
            "tipo": "template",
            "template_nome": "lembrete_24h",
            "variaveis": {"nome": "Ana", "servico": "corte", "data_hora": "quinta, 15h"},
        },
    )
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["status"] == "enviada"
    assert "Ana" in corpo["corpo_renderizado"]
    assert len(transporte.requisicoes) == 1


def test_template_inexistente_nao_sai(client, canal_configurado):
    canal_configurado()
    resposta = client.post(
        "/canal/enviar",
        json={"destinatario": TELEFONE, "tipo": "template", "template_nome": "nao_existe"},
    )
    assert resposta.status_code == 409
    assert resposta.json()["code"] == "TEMPLATE_INEXISTENTE"


def test_optout_bloqueia_envio_ativo(client, canal_configurado, org_id):
    transporte = canal_configurado()
    from app.db import SessionLocal, sessao_org
    from app.models import ChannelOptout

    with SessionLocal() as db:
        sessao_org(db, org_id)
        db.add(ChannelOptout(org_id=org_id, telefone=TELEFONE, origem="palavra_chave"))
        db.commit()

    resposta = client.post(
        "/canal/enviar",
        json={
            "destinatario": TELEFONE,
            "tipo": "template",
            "template_nome": "lembrete_24h",
            "variaveis": {"nome": "Ana", "servico": "corte", "data_hora": "quinta, 15h"},
        },
    )
    assert resposta.status_code == 403
    assert resposta.json()["code"] == "OPTOUT_ATIVO"
    assert transporte.requisicoes == []  # nada saiu pelo driver


def test_idempotency_key_nao_reenvia(client, canal_configurado):
    transporte = canal_configurado()
    corpo = {
        "destinatario": TELEFONE,
        "tipo": "template",
        "template_nome": "lembrete_24h",
        "variaveis": {"nome": "Ana", "servico": "corte", "data_hora": "quinta, 15h"},
    }
    headers = {"Idempotency-Key": "lembrete-1"}
    primeira = client.post("/canal/enviar", json=corpo, headers=headers)
    segunda = client.post("/canal/enviar", json=corpo, headers=headers)
    assert primeira.json()["message_id"] == segunda.json()["message_id"]
    assert len(transporte.requisicoes) == 1


def test_numero_pessoal_e_recusado(client, transporte):
    resposta = client.post(
        "/canal/config",
        json={
            "driver": "evolution",
            "numero": "+5511911112222",
            "instancia": "org-x",
            "credenciais": {"server_url": "http://x", "instancia": "org-x", "apikey": "k"},
            "confirmo_numero_dedicado": False,
        },
    )
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "NUMERO_PESSOAL_RECUSADO"
