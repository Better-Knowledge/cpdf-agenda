# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""T-05: a tela de grade lista regras e bloqueios pela API pública."""

from .conftest import integracao

pytestmark = integracao


def test_bloqueios_futuros_sao_listados(client, catalogo):
    recurso = catalogo["recurso"]["id"]
    criado = client.post(
        "/availability/blocks",
        json={
            "resource_id": recurso,
            "inicio": "2026-12-24T00:00:00-03:00",
            "fim": "2026-12-26T23:59:00-03:00",
            "motivo": "Natal",
        },
    )
    assert criado.status_code == 201
    # bloqueio já encerrado não aparece na listagem
    client.post(
        "/availability/blocks",
        json={
            "resource_id": recurso,
            "inicio": "2020-01-01T08:00:00-03:00",
            "fim": "2020-01-01T12:00:00-03:00",
            "motivo": "antigo",
        },
    )
    lista = client.get("/availability/blocks", params={"resource_id": recurso}).json()
    motivos = [b["motivo"] for b in lista]
    assert "Natal" in motivos
    assert "antigo" not in motivos


def test_grade_semanal_listada(client, catalogo):
    regras = client.get("/availability/rules").json()
    assert len(regras) == 5  # seg–sex do fixture
    assert all(r["hora_inicio"] == "09:00:00" for r in regras)
