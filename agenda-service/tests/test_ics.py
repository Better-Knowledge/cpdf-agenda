# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""RF-11 — o feed .ics e o que ele deliberadamente não conta.

O token na URL é o único segredo: não há autenticação nesta rota. Os testes
cobrem as três consequências disso — revogação vale na hora, o modo privado
esconde o cliente, e a URL nunca volta inteira numa listagem.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.ics import Evento, gerar

from .conftest import integracao

# ── Geração do arquivo (sem banco) ───────────────────────────────────────────


def test_o_arquivo_segue_o_rfc_5545():
    agora = datetime(2027, 3, 9, 12, 0, tzinfo=UTC)
    texto = gerar(
        "Agenda",
        [
            Evento(
                uid="abc@agenda",
                inicio=datetime(2027, 3, 9, 13, 0, tzinfo=UTC),
                fim=datetime(2027, 3, 9, 14, 0, tzinfo=UTC),
                titulo="Corte — Ana",
            )
        ],
        agora,
    )
    assert texto.startswith("BEGIN:VCALENDAR\r\n")
    assert texto.endswith("END:VCALENDAR\r\n")
    assert "\r\nDTSTART:20270309T130000Z\r\n" in texto
    assert "\r\nDTEND:20270309T140000Z\r\n" in texto
    # Toda linha termina em CRLF — o Google recusa LF puro
    assert "\n" not in texto.replace("\r\n", "")


def test_caracteres_especiais_sao_escapados():
    texto = gerar(
        "Agenda",
        [
            Evento(
                uid="x@agenda",
                inicio=datetime(2027, 3, 9, 13, 0, tzinfo=UTC),
                fim=datetime(2027, 3, 9, 14, 0, tzinfo=UTC),
                titulo="Corte; barba, sobrancelha",
            )
        ],
        datetime(2027, 3, 9, tzinfo=UTC),
    )
    assert r"SUMMARY:Corte\; barba\, sobrancelha" in texto


def test_linha_longa_dobra_sem_partir_acento():
    """Dobra em 75 **octetos**: contar caracteres partiria um 'ã' ao meio e o
    arquivo viraria lixo no cliente de calendário."""
    titulo = "Sessão de acompanhamento com avaliação " * 4
    texto = gerar(
        "Agenda",
        [
            Evento(
                uid="y@agenda",
                inicio=datetime(2027, 3, 9, 13, 0, tzinfo=UTC),
                fim=datetime(2027, 3, 9, 14, 0, tzinfo=UTC),
                titulo=titulo,
            )
        ],
        datetime(2027, 3, 9, tzinfo=UTC),
    )
    for linha in texto.split("\r\n"):
        assert len(linha.encode()) <= 75, linha
    # e o conteúdo continua legível depois de desdobrar
    desdobrado = texto.replace("\r\n ", "")
    assert titulo.replace(",", "\\,") in desdobrado


# ── A rota (com banco) ───────────────────────────────────────────────────────

pytestmark_integracao = integracao


@pytest.fixture()
def agendado(client, catalogo):
    inicio = (datetime.now(UTC) + timedelta(days=3)).replace(
        hour=13, minute=0, second=0, microsecond=0
    )
    resposta = client.post(
        "/appointments",
        json={
            "service_id": catalogo["servico"]["id"],
            "resource_id": catalogo["recurso"]["id"],
            "inicio": inicio.isoformat(),
            "cliente_nome": "Ana Prado",
            "cliente_telefone": "+5511977776666",
        },
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


@integracao
def test_criar_devolve_a_url_uma_vez_e_a_listagem_redige(client, catalogo):
    criado = client.post("/ics/tokens", json={"resource_id": catalogo["recurso"]["id"]}).json()
    assert criado["url_completa"].endswith(".ics")
    assert "***" not in criado["url_completa"]

    (listado,) = client.get("/ics/tokens").json()
    assert "***" in listado["url"]
    assert listado["url"] != criado["url_completa"]
    # o token não vaza por nenhum outro campo da listagem
    import json

    token = criado["url_completa"].rsplit("/", 1)[1].removesuffix(".ics")
    assert token not in json.dumps(listado)


@integracao
def test_o_feed_publico_nao_exige_credencial(client, agendado):
    url = client.post("/ics/tokens", json={}).json()["url_completa"]
    caminho = "/ics/" + url.rsplit("/", 1)[1]

    resposta = client.get(caminho, headers={"X-Org-Id": ""})
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/calendar")
    assert "Ana Prado" in resposta.text
    assert f"UID:{agendado['id']}@" in resposta.text


@integracao
def test_modo_privado_mostra_ocupado_e_nada_mais(client, agendado):
    url = client.post("/ics/tokens", json={"modo": "privado"}).json()["url_completa"]
    corpo = client.get("/ics/" + url.rsplit("/", 1)[1], headers={"X-Org-Id": ""}).text
    assert "SUMMARY:Ocupado" in corpo
    assert "Ana Prado" not in corpo
    assert "+5511977776666" not in corpo


@integracao
def test_cancelado_sai_do_feed(client, agendado):
    url = client.post("/ics/tokens", json={}).json()["url_completa"]
    caminho = "/ics/" + url.rsplit("/", 1)[1]
    assert agendado["id"] in client.get(caminho, headers={"X-Org-Id": ""}).text

    client.post(f"/appointments/{agendado['id']}/cancel", json={"motivo": "cliente pediu"})
    assert agendado["id"] not in client.get(caminho, headers={"X-Org-Id": ""}).text


@integracao
def test_revogar_derruba_a_url_na_hora(client, agendado):
    criado = client.post("/ics/tokens", json={}).json()
    caminho = "/ics/" + criado["url_completa"].rsplit("/", 1)[1]
    assert client.get(caminho, headers={"X-Org-Id": ""}).status_code == 200

    client.post(f"/ics/tokens/{criado['id']}/revogar")
    negado = client.get(caminho, headers={"X-Org-Id": ""})
    assert negado.status_code == 404
    # e o 404 não confirma que o token existiu
    assert negado.json()["code"] == "NAO_ENCONTRADO"


@integracao
def test_token_de_outra_org_nao_ve_nada_desta(client, agendado, banco_migrado):
    """A rota é pública, mas a leitura continua presa à org do token."""
    import uuid

    from app.models import IcsToken
    from app.sessao import SessionLocal, sessao_org

    outra = uuid.uuid4()
    with SessionLocal() as db:
        sessao_org(db, outra)
        db.add(IcsToken(org_id=outra, token="token-de-outra-org", modo="completo"))
        db.commit()

    corpo = client.get("/ics/token-de-outra-org.ics", headers={"X-Org-Id": ""}).text
    assert "BEGIN:VCALENDAR" in corpo
    assert "Ana Prado" not in corpo
    assert agendado["id"] not in corpo


@integracao
def test_atendimento_nao_cria_feed_de_calendario(client, catalogo, org_id):
    """Um feed é a agenda inteira do recurso numa URL sem autenticação — é
    poder administrativo, não de quem atende um cliente."""
    from app.auth import credencial_atual
    from app.main import app

    from .conftest import credencial_falsa

    app.dependency_overrides[credencial_atual] = credencial_falsa(
        org_id, "atendimento", titular="+5511977776666"
    )
    try:
        recusado = client.post("/ics/tokens", json={})
        assert recusado.status_code == 403
        assert recusado.json()["code"] == "ESCOPO_INSUFICIENTE"
    finally:
        app.dependency_overrides.pop(credencial_atual, None)
