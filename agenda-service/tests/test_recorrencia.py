# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""RF-15 — Recorrência simples: série semanal/quinzenal por ocorrências ou data-fim."""

from .conftest import integracao

pytestmark = integracao

# 2026-09-08 é uma terça — dentro da grade seg–sex do fixture
TERCA_10H = "2026-09-08T10:00:00-03:00"


def _serie(client, catalogo, **extra):
    corpo = {
        "service_id": catalogo["servico"]["id"],
        "resource_id": catalogo["recurso"]["id"],
        "inicio": TERCA_10H,
        "cliente_nome": "Cliente Fiel",
        "cliente_telefone": "+5511977770000",
        "frequencia": "semanal",
        "ocorrencias": 4,
        **extra,
    }
    return client.post("/appointments/recorrentes", json=corpo)


def test_serie_semanal_cria_uma_ocorrencia_por_semana(client, catalogo):
    resposta = _serie(client, catalogo)
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["conflitos"] == []
    assert len(corpo["criadas"]) == 4
    dias = [c["inicio"][:10] for c in corpo["criadas"]]
    assert dias == ["2026-09-08", "2026-09-15", "2026-09-22", "2026-09-29"]
    # toda ocorrência é um appointment próprio ligado à série
    assert all(c["series_id"] == corpo["series_id"] for c in corpo["criadas"])
    assert all(c["label_humano"].startswith("terça") for c in corpo["criadas"])


def test_serie_quinzenal_com_data_fim(client, catalogo):
    resposta = _serie(
        client,
        catalogo,
        frequencia="quinzenal",
        ocorrencias=None,
        fim_em="2026-10-10",
        inicio="2026-09-09T14:00:00-03:00",  # quarta
    )
    assert resposta.status_code == 201, resposta.text
    dias = [c["inicio"][:10] for c in resposta.json()["criadas"]]
    assert dias == ["2026-09-09", "2026-09-23", "2026-10-07"]  # passo de 14 dias até o fim


def test_conflito_nao_quebra_a_serie(client, catalogo):
    # ocupa a 2ª ocorrência antes de criar a série
    ocupado = client.post(
        "/appointments",
        json={
            "service_id": catalogo["servico"]["id"],
            "resource_id": catalogo["recurso"]["id"],
            "inicio": "2026-09-15T10:00:00-03:00",
            "cliente_nome": "Outro Cliente",
            "cliente_telefone": "+5511966660000",
        },
    )
    assert ocupado.status_code == 201

    resposta = _serie(client, catalogo)
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert len(corpo["criadas"]) == 3  # 1ª, 3ª e 4ª entraram
    assert [c["inicio"][:10] for c in corpo["criadas"]] == [
        "2026-09-08",
        "2026-09-22",
        "2026-09-29",
    ]
    (conflito,) = corpo["conflitos"]
    assert conflito["inicio"][:10] == "2026-09-15"
    assert len(conflito["alternativas"]) == 3  # pendente já com propostas


def test_ocorrencias_e_fim_em_juntos_e_recusado(client, catalogo):
    resposta = _serie(client, catalogo, fim_em="2026-12-01")
    assert resposta.status_code == 422


def test_cancelar_uma_ocorrencia_nao_afeta_as_outras(client, catalogo):
    serie = _serie(client, catalogo).json()
    segunda_ocorrencia = serie["criadas"][1]
    cancelada = client.post(
        f"/appointments/{segunda_ocorrencia['id']}/cancel", json={"motivo": "viagem"}
    )
    assert cancelada.status_code == 200

    dia = client.get("/appointments", params={"date": "2026-09-22"}).json()
    da_serie = [c for c in dia if c["series_id"] == serie["series_id"]]
    assert da_serie[0]["status"] == "agendado"  # 3ª ocorrência intacta


def test_cancelar_todas_as_futuras(client, catalogo):
    serie = _serie(client, catalogo).json()
    resposta = client.post(
        f"/appointments/recorrentes/{serie['series_id']}/cancel",
        json={"motivo": "cliente encerrou o pacote"},
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["canceladas"] == 4

    # os slots voltaram para a grade: dá para agendar no horário da 1ª ocorrência
    liberado = client.post(
        "/appointments",
        json={
            "service_id": catalogo["servico"]["id"],
            "resource_id": catalogo["recurso"]["id"],
            "inicio": TERCA_10H,
            "cliente_nome": "Novo Cliente",
            "cliente_telefone": "+5511955550000",
        },
    )
    assert liberado.status_code == 201


def test_agente_cancela_serie_so_com_confirmacao_humana(client, catalogo, org_id):
    serie = _serie(client, catalogo).json()

    from app.auth import Credencial, credencial_atual
    from app.main import app

    app.dependency_overrides[credencial_atual] = lambda: Credencial(org_id=org_id, ator="agente")
    try:
        primeira = client.post(
            f"/appointments/recorrentes/{serie['series_id']}/cancel", json={"motivo": "fim"}
        )
        assert primeira.status_code == 409
        corpo = primeira.json()
        assert corpo["code"] == "CONFIRMACAO_NECESSARIA"
        assert corpo["previa"]["ocorrencias_futuras"] == 4

        segunda = client.post(
            f"/appointments/recorrentes/{serie['series_id']}/cancel",
            json={"motivo": "fim", "confirmation_token": corpo["confirmation_token"]},
        )
        assert segunda.status_code == 200
        assert segunda.json()["canceladas"] == 4
    finally:
        app.dependency_overrides.pop(credencial_atual)
