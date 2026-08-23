# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""RF-06 — Reagendamento atômico e cancelamento que devolve o slot."""

from .conftest import integracao

pytestmark = integracao


def _agendar(client, catalogo, inicio):
    return client.post(
        "/appointments",
        json={
            "service_id": catalogo["servico"]["id"],
            "resource_id": catalogo["recurso"]["id"],
            "inicio": inicio,
            "cliente_nome": "Cliente",
            "cliente_telefone": "+5511988887777",
        },
    )


def test_reagendar_para_slot_ocupado_nao_muda_nada(client, catalogo):
    meu = _agendar(client, catalogo, "2026-08-27T09:00:00-03:00").json()
    _agendar(client, catalogo, "2026-08-27T14:00:00-03:00")

    resposta = client.post(
        f"/appointments/{meu['id']}/reschedule",
        json={"novo_inicio": "2026-08-27T14:00:00-03:00"},
    )
    assert resposta.status_code == 409
    assert resposta.json()["code"] == "SLOT_INDISPONIVEL"

    # atômico: o horário original continua reservado (tentar ocupá-lo falha)
    assert _agendar(client, catalogo, "2026-08-27T09:00:00-03:00").status_code == 409


def test_reagendar_libera_o_slot_antigo_na_mesma_transacao(client, catalogo):
    meu = _agendar(client, catalogo, "2026-08-27T09:00:00-03:00").json()
    resposta = client.post(
        f"/appointments/{meu['id']}/reschedule",
        json={"novo_inicio": "2026-08-27T15:00:00-03:00"},
    )
    assert resposta.status_code == 200
    assert resposta.json()["label_humano"] == "quinta, 27 de agosto, 15h"
    # o slot antigo voltou para a grade na hora
    assert _agendar(client, catalogo, "2026-08-27T09:00:00-03:00").status_code == 201


def test_cancelamento_por_agente_exige_confirmacao_humana(client, catalogo, org_id):
    meu = _agendar(client, catalogo, "2026-08-27T11:00:00-03:00").json()

    # credencial de agente (fase 1: API key mapeada) — simulada trocando o ator
    from app.auth import Credencial, credencial_atual
    from app.main import app

    app.dependency_overrides[credencial_atual] = lambda: Credencial(
        org_id=org_id, ator="agente"
    )
    try:
        primeira = client.post(
            f"/appointments/{meu['id']}/cancel", json={"motivo": "cliente desistiu"}
        )
        assert primeira.status_code == 409
        corpo = primeira.json()
        assert corpo["code"] == "CONFIRMACAO_NECESSARIA"
        token = corpo["confirmation_token"]

        segunda = client.post(
            f"/appointments/{meu['id']}/cancel",
            json={"motivo": "cliente desistiu", "confirmation_token": token},
        )
        assert segunda.status_code == 200
        assert segunda.json()["status"] == "cancelado"
    finally:
        app.dependency_overrides.pop(credencial_atual)

    # cancelou: o slot volta imediatamente para a grade
    assert _agendar(client, catalogo, "2026-08-27T11:00:00-03:00").status_code == 201


def test_historico_registra_origem_e_motivo(client, catalogo):
    meu = _agendar(client, catalogo, "2026-09-01T09:00:00-03:00").json()
    client.post(
        f"/appointments/{meu['id']}/reschedule",
        json={"novo_inicio": "2026-09-01T10:00:00-03:00", "motivo": "pedido do cliente"},
    )
    historico = client.get(f"/appointments/{meu['id']}/history").json()
    acoes = [h["acao"] for h in historico]
    assert acoes == ["criado", "reagendado"]
    assert historico[1]["motivo"] == "pedido do cliente"
