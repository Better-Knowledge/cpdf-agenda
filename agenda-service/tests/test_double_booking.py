"""RF-04 — Zero double-booking: a regra vive no banco.

10 requisições simultâneas para o mesmo slot → 1 sucesso e 9 recusas
legíveis com alternativas no payload.
"""

from concurrent.futures import ThreadPoolExecutor

from .conftest import integracao

pytestmark = integracao

SLOT = "2026-08-27T10:00:00-03:00"  # quinta dentro da grade do fixture


def _agendar(client, catalogo, nome: str, inicio: str = SLOT):
    return client.post(
        "/appointments",
        json={
            "service_id": catalogo["servico"]["id"],
            "resource_id": catalogo["recurso"]["id"],
            "inicio": inicio,
            "cliente_nome": nome,
            "cliente_telefone": "+5511999990000",
        },
    )


def test_dez_requisicoes_simultaneas_uma_vence(client, catalogo):
    with ThreadPoolExecutor(max_workers=10) as pool:
        respostas = list(
            pool.map(lambda i: _agendar(client, catalogo, f"Cliente {i}"), range(10))
        )
    codigos = sorted(r.status_code for r in respostas)
    assert codigos == [201] + [409] * 9

    recusas = [r.json() for r in respostas if r.status_code == 409]
    for erro in recusas:
        assert erro["code"] == "SLOT_INDISPONIVEL"
        assert erro["hint"]  # o agente lê o hint e oferece as alternativas
        assert len(erro["alternativas"]) == 3
        # nenhuma alternativa é o próprio slot em disputa
        assert all(a["inicio"] != SLOT for a in erro["alternativas"])


def test_sobreposicao_parcial_conflita_no_banco(client, catalogo):
    assert _agendar(client, catalogo, "A", "2026-08-28T11:00:00-03:00").status_code == 201
    resposta = _agendar(client, catalogo, "B", "2026-08-28T11:30:00-03:00")
    assert resposta.status_code == 409
    assert resposta.json()["code"] == "SLOT_INDISPONIVEL"


def test_buffer_do_compromisso_existente_sai_da_oferta(client, catalogo):
    # buffer_depois de 10 min: 11h00 termina 12h10 — a grade não oferece 12h00
    assert _agendar(client, catalogo, "A", "2026-09-04T11:00:00-03:00").status_code == 201
    slots = client.get(
        "/slots",
        params={
            "service_id": catalogo["servico"]["id"],
            "from": "2026-09-04T09:00:00-03:00",
            "to": "2026-09-04T18:00:00-03:00",
        },
    ).json()
    inicios = {s["inicio"][11:16] for s in slots}
    assert "12:00" not in inicios
    assert "12:30" in inicios  # 12h30 já respeita o buffer


def test_idempotency_key_nao_duplica_agendamento(client, catalogo):
    headers = {"Idempotency-Key": "agendamento-teste-1"}
    corpo = {
        "service_id": catalogo["servico"]["id"],
        "resource_id": catalogo["recurso"]["id"],
        "inicio": "2026-08-31T09:00:00-03:00",
        "cliente_nome": "Cliente",
        "cliente_telefone": "+5511999990000",
    }
    primeira = client.post("/appointments", json=corpo, headers=headers)
    segunda = client.post("/appointments", json=corpo, headers=headers)
    assert primeira.status_code == 201
    assert segunda.status_code == 201
    assert segunda.json()["id"] == primeira.json()["id"]
