"""Alterar e excluir: serviços (soft delete), janelas de grade e bloqueios."""

from .conftest import integracao

pytestmark = integracao


def test_alterar_duracao_nao_mexe_em_agendamento_existente(client, catalogo):
    """Critério do RF-01, agora protegido por teste."""
    servico = catalogo["servico"]["id"]
    criado = client.post(
        "/appointments",
        json={
            "service_id": servico,
            "resource_id": catalogo["recurso"]["id"],
            "inicio": "2026-09-03T10:00:00-03:00",
            "cliente_nome": "Cliente",
            "cliente_telefone": "+5511999990000",
        },
    ).json()

    alterado = client.patch(f"/services/{servico}", json={"duracao_min": 30, "preco": "95.00"})
    assert alterado.status_code == 200
    assert alterado.json()["duracao_min"] == 30
    assert alterado.json()["preco"] == "95.00"

    dia = client.get("/appointments", params={"date": "2026-09-03"}).json()
    compromisso = next(c for c in dia if c["id"] == criado["id"])
    assert compromisso["fim"] == criado["fim"]  # continua com os 60 min originais


def test_excluir_servico_e_soft_delete(client, catalogo):
    servico = catalogo["servico"]["id"]
    resposta = client.delete(f"/services/{servico}")
    assert resposta.status_code == 200
    assert resposta.json()["ativo"] is False

    ativos = [s["id"] for s in client.get("/services").json()["items"]]
    assert servico not in ativos
    inativos = [s["id"] for s in client.get("/services?ativo=false").json()["items"]]
    assert servico in inativos

    # serviço desativado não agenda nem oferece slot
    negado = client.post(
        "/appointments",
        json={
            "service_id": servico,
            "inicio": "2026-09-03T10:00:00-03:00",
            "cliente_nome": "X",
            "cliente_telefone": "+5511999990000",
        },
    )
    assert negado.status_code == 404

    # reativar é um PATCH — exclusão nunca perde dado
    reativado = client.patch(f"/services/{servico}", json={"ativo": True})
    assert reativado.json()["ativo"] is True


def test_remover_janela_da_grade_apaga_oferta(client, catalogo):
    regras = client.get("/availability/rules").json()
    quinta = next(r for r in regras if r["dia_semana"] == 3)
    removida = client.delete(f"/availability/rules/{quinta['id']}")
    assert removida.json()["removida"] is True

    slots = client.get(
        "/slots",
        params={
            "service_id": catalogo["servico"]["id"],
            "from": "2026-09-10T00:00:00-03:00",  # uma quinta
            "to": "2026-09-10T23:59:00-03:00",
        },
    ).json()
    assert slots == []

    # idempotente: remover de novo não é erro
    assert client.delete(f"/availability/rules/{quinta['id']}").json()["removida"] is False


def test_alterar_janela_valida_periodo(client, catalogo):
    regras = client.get("/availability/rules").json()
    segunda = next(r for r in regras if r["dia_semana"] == 0)
    invalido = client.patch(
        f"/availability/rules/{segunda['id']}", json={"hora_fim": "08:00"}
    )
    assert invalido.status_code == 400
    assert invalido.json()["code"] == "PERIODO_INVALIDO"

    ok = client.patch(f"/availability/rules/{segunda['id']}", json={"hora_fim": "12:00"})
    assert ok.status_code == 200
    assert ok.json()["hora_fim"] == "12:00:00"


def test_remover_bloqueio_devolve_horarios(client, catalogo):
    recurso = catalogo["recurso"]["id"]
    bloqueio = client.post(
        "/availability/blocks",
        json={
            "resource_id": recurso,
            "inicio": "2026-09-11T00:00:00-03:00",  # sexta inteira
            "fim": "2026-09-11T23:59:00-03:00",
            "motivo": "manutenção",
        },
    ).json()

    def slots_sexta():
        return client.get(
            "/slots",
            params={
                "service_id": catalogo["servico"]["id"],
                "from": "2026-09-11T00:00:00-03:00",
                "to": "2026-09-11T23:59:00-03:00",
            },
        ).json()

    assert slots_sexta() == []
    assert client.delete(f"/availability/blocks/{bloqueio['id']}").json()["removido"] is True
    assert len(slots_sexta()) > 0
