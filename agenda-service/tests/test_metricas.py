# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""T-10 — as métricas do §4.

O que estes testes protegem é menos a aritmética e mais a honestidade dos
números: denominador vazio não vira zero, no-show não se dilui no futuro, e
a origem distingue conversa de link público.
"""

from datetime import UTC, datetime, timedelta

from .conftest import integracao

pytestmark = integracao


def _dia_util(daqui_a: int, hora: int = 10) -> datetime:
    from app.tempo import TZ

    dia = (datetime.now(TZ) + timedelta(days=daqui_a)).replace(
        hour=hora, minute=0, second=0, microsecond=0
    )
    while dia.weekday() > 4:
        dia += timedelta(days=1)
    return dia


def _agendar(client, catalogo, quando: datetime, nome="Ana"):
    resposta = client.post(
        "/appointments",
        json={
            "service_id": catalogo["servico"]["id"],
            "resource_id": catalogo["recurso"]["id"],
            "inicio": quando.isoformat(),
            "cliente_nome": nome,
            "cliente_telefone": "+5511911112222",
        },
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _metricas(client, de: datetime, ate: datetime) -> dict:
    resposta = client.get(
        "/metricas", params={"de": de.date().isoformat(), "ate": ate.date().isoformat()}
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def test_periodo_vazio_nao_inventa_zero(client, catalogo):
    """Sem compromisso nenhum, 'no-show de 0%' seria uma afirmação falsa: não
    houve base para calcular."""
    daqui = _dia_util(30)
    m = _metricas(client, daqui, daqui)
    assert m["total"] == 0
    assert m["pct_no_show"] is None
    assert m["pct_por_conversa"] is None
    assert m["pct_ocupacao"] == 0.0  # a grade existe; o que faltou foi compromisso


def test_conta_por_origem_e_por_status(client, catalogo):
    dia = _dia_util(12)
    _agendar(client, catalogo, dia)
    segundo = _agendar(client, catalogo, dia + timedelta(hours=2), nome="Bruno")
    client.post(f"/appointments/{segundo['id']}/confirm")

    m = _metricas(client, dia, dia)
    assert m["total"] == 2
    assert m["por_origem"]["agente"] == 2
    assert m["pct_por_conversa"] == 100.0
    assert m["por_status"]["confirmado"] == 1
    assert m["pct_confirmados"] == 50.0
    assert "compromissos" in m["narrativa"]


def test_o_link_publico_aparece_separado_da_conversa(client, catalogo):
    dia = _dia_util(14)
    _agendar(client, catalogo, dia)
    link = client.post("/booking-links", json={"service_id": catalogo["servico"]["id"]}).json()
    client.post(
        f"/publico/agendar/{link['slug']}",
        json={
            "cliente_nome": "Pelo link",
            "cliente_telefone": "+5511933334444",
            "inicio": (dia + timedelta(hours=3)).isoformat(),
        },
        headers={"X-Org-Id": ""},
    )
    m = _metricas(client, dia, dia)
    assert m["por_origem"] == {"agente": 1, "cliente": 1}
    assert m["pct_por_conversa"] == 50.0


def test_ocupacao_usa_a_grade_como_denominador(client, catalogo):
    """Uma hora agendada num dia de 9 horas de grade é ~11% de ocupação."""
    dia = _dia_util(16)
    _agendar(client, catalogo, dia)
    m = _metricas(client, dia, dia)
    assert m["pct_ocupacao"] == 11.1


def test_no_show_nao_conta_o_futuro_no_denominador(client, catalogo, banco_migrado, org_id):
    """Sem esta regra, a taxa de faltas cairia sozinha à medida que a agenda
    de amanhã enche — o número melhoraria sem nada melhorar."""
    from sqlalchemy.dialects.postgresql import Range

    from app.models import Appointment
    from app.sessao import SessionLocal, sessao_org

    passado = datetime.now(UTC) - timedelta(days=3)
    futuro = _dia_util(20)
    _agendar(client, catalogo, futuro)

    with SessionLocal() as db:
        sessao_org(db, org_id)
        db.add(
            Appointment(
                org_id=org_id,
                service_id=catalogo["servico"]["id"],
                resource_id=catalogo["recurso"]["id"],
                cliente_nome="Faltou",
                cliente_telefone="+5511955556666",
                periodo=Range(passado, passado + timedelta(hours=1)),
                status="no_show",
            )
        )
        db.commit()

    m = _metricas(client, passado, futuro)
    assert m["total"] == 2
    assert m["pct_no_show"] == 100.0  # 1 falta em 1 compromisso já passado


def test_atendimento_nao_ve_metricas(client, catalogo, org_id):
    from app.auth import credencial_atual
    from app.main import app

    from .conftest import credencial_falsa

    app.dependency_overrides[credencial_atual] = credencial_falsa(
        org_id, "atendimento", titular="+5511911112222"
    )
    try:
        hoje = _dia_util(0).date().isoformat()
        recusado = client.get("/metricas", params={"de": hoje, "ate": hoje})
        assert recusado.status_code == 403
    finally:
        app.dependency_overrides.pop(credencial_atual, None)
