# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""RF-13 — o link público de auto-agendamento.

A propriedade que estes testes protegem não é "dá para agendar clicando" —
é que a página pública **não é um caminho privilegiado**. Ela passa pela
mesma constraint, cria o mesmo compromisso, e não devolve nada sobre a
agenda além dos horários livres.
"""

from datetime import datetime, timedelta

from .conftest import integracao

pytestmark = integracao


def _dia_util(daqui_a: int = 4, hora: int = 14) -> datetime:
    from app.tempo import TZ

    dia = (datetime.now(TZ) + timedelta(days=daqui_a)).replace(
        hour=hora, minute=0, second=0, microsecond=0
    )
    while dia.weekday() > 4:
        dia += timedelta(days=1)
    return dia


def _link(client, catalogo, **extra) -> dict:
    resposta = client.post(
        "/booking-links", json={"service_id": catalogo["servico"]["id"], **extra}
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def test_o_slug_sai_do_nome_do_servico(client, catalogo):
    link = _link(client, catalogo)
    assert link["slug"] == "corte"
    assert link["url"].endswith("/app/agendar/corte")
    assert link["ativo"] is True
    assert link["exige_caucao"] is False  # caução nasce desligada (RF-13)


def test_slug_repetido_ganha_sufixo(client, catalogo):
    primeiro = _link(client, catalogo)
    segundo = _link(client, catalogo)
    assert primeiro["slug"] != segundo["slug"]
    assert segundo["slug"].startswith("corte-")


def test_a_pagina_publica_mostra_o_minimo(client, catalogo):
    link = _link(client, catalogo, exige_caucao=True, valor_caucao="30.00")
    corpo = client.get(f"/publico/agendar/{link['slug']}", headers={"X-Org-Id": ""}).json()

    assert corpo == {
        "slug": link["slug"],
        "servico": "Corte",
        "duracao_min": 60,
        "preco": "80.00",
        "exige_caucao": True,
        "valor_caucao": "30.00",
        "aviso_caucao": corpo["aviso_caucao"],
    }
    assert "30.00" in corpo["aviso_caucao"]
    # nada de recurso, org, telefone ou compromisso vaza para a página
    import json

    assert catalogo["recurso"]["id"] not in json.dumps(corpo)


def test_agendar_pelo_link_usa_o_mesmo_caminho(client, catalogo):
    link = _link(client, catalogo)
    inicio = _dia_util()
    criado = client.post(
        f"/publico/agendar/{link['slug']}",
        json={
            "cliente_nome": "Ana Prado",
            "cliente_telefone": "+55 11 99999-8888",
            "inicio": inicio.isoformat(),
        },
        headers={"X-Org-Id": ""},
    )
    assert criado.status_code == 201, criado.text
    corpo = criado.json()
    assert corpo["label_humano"]

    # o compromisso existe na agenda do prestador, com origem 'cliente'
    resposta = client.get("/appointments", params={"date": inicio.date().isoformat()})
    assert resposta.status_code == 200, resposta.text
    (detalhe,) = [a for a in resposta.json() if a["id"] == corpo["id"]]
    assert detalhe["origem"] == "cliente"
    assert detalhe["cliente_nome"] == "Ana Prado"
    # e o telefone entrou canônico, não como o cliente digitou
    assert detalhe["cliente_telefone"] == "+5511999998888"


def test_horario_ocupado_devolve_alternativas(client, catalogo):
    link = _link(client, catalogo)
    inicio = _dia_util(daqui_a=5)
    corpo = {"cliente_nome": "Ana", "cliente_telefone": "+5511999998888", "inicio": inicio.isoformat()}
    assert client.post(f"/publico/agendar/{link['slug']}", json=corpo, headers={"X-Org-Id": ""}).status_code == 201

    conflito = client.post(
        f"/publico/agendar/{link['slug']}",
        json={**corpo, "cliente_nome": "Bruno"},
        headers={"X-Org-Id": ""},
    )
    assert conflito.status_code == 409
    erro = conflito.json()
    assert erro["code"] == "SLOT_INDISPONIVEL"
    assert len(erro["alternativas"]) == 3  # o cliente recebe opção, não "não tem"


def test_link_desativado_explica_em_vez_de_sumir(client, catalogo):
    link = _link(client, catalogo)
    client.delete(f"/booking-links/{link['id']}")

    resposta = client.get(f"/publico/agendar/{link['slug']}", headers={"X-Org-Id": ""})
    assert resposta.status_code == 409
    assert resposta.json()["code"] == "LINK_INATIVO"
    assert "WhatsApp" in resposta.json()["hint"]


def test_slots_publicos_so_mostram_livres(client, catalogo):
    link = _link(client, catalogo)
    dia = _dia_util(daqui_a=6, hora=9)
    params = {"from": dia.isoformat(), "to": dia.replace(hour=18).isoformat()}
    antes = client.get(f"/publico/agendar/{link['slug']}/slots", params=params, headers={"X-Org-Id": ""}).json()
    assert antes

    client.post(
        f"/publico/agendar/{link['slug']}",
        json={
            "cliente_nome": "Ana",
            "cliente_telefone": "+5511999998888",
            "inicio": antes[0]["inicio"],
        },
        headers={"X-Org-Id": ""},
    )
    depois = client.get(f"/publico/agendar/{link['slug']}/slots", params=params, headers={"X-Org-Id": ""}).json()
    assert [s["inicio"] for s in depois] != [s["inicio"] for s in antes]
    assert antes[0]["inicio"] not in [s["inicio"] for s in depois]


def test_o_limite_por_ip_barra_a_enxurrada(client, catalogo):
    """Criar compromisso mexe na agenda de alguém: o limite de escrita é
    estreito de propósito, e a resposta diz quanto esperar."""
    link = _link(client, catalogo)
    inicio = _dia_util(daqui_a=7, hora=9)
    for i in range(5):
        client.post(
            f"/publico/agendar/{link['slug']}",
            json={
                "cliente_nome": f"Cliente {i}",
                "cliente_telefone": "+5511999998888",
                "inicio": (inicio + timedelta(hours=i)).isoformat(),
            },
            headers={"X-Org-Id": ""},
        )
    barrado = client.post(
        f"/publico/agendar/{link['slug']}",
        json={
            "cliente_nome": "Sexto",
            "cliente_telefone": "+5511999998888",
            "inicio": (inicio + timedelta(hours=6)).isoformat(),
        },
        headers={"X-Org-Id": ""},
    )
    assert barrado.status_code == 429
    assert barrado.json()["code"] == "MUITAS_REQUISICOES"
    assert barrado.json()["retryable"] is True


def test_horario_no_passado_e_recusado(client, catalogo):
    link = _link(client, catalogo)
    ontem = datetime.now().astimezone() - timedelta(days=1)
    resposta = client.post(
        f"/publico/agendar/{link['slug']}",
        json={
            "cliente_nome": "Ana",
            "cliente_telefone": "+5511999998888",
            "inicio": ontem.isoformat(),
        },
        headers={"X-Org-Id": ""},
    )
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "DATA_NO_PASSADO"


def test_atendimento_nao_cria_link_publico(client, catalogo, org_id):
    from app.auth import credencial_atual
    from app.main import app

    from .conftest import credencial_falsa

    app.dependency_overrides[credencial_atual] = credencial_falsa(
        org_id, "atendimento", titular="+5511999998888"
    )
    try:
        recusado = client.post("/booking-links", json={"service_id": catalogo["servico"]["id"]})
        assert recusado.status_code == 403
    finally:
        app.dependency_overrides.pop(credencial_atual, None)
