# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""IA-03 — risco de no-show determinístico e explicável.

O ponto destes testes não é o número em si: é que o número seja sempre
justificado por parcelas que alguém consegue conferir a olho — e que o
efeito do risco alto seja pedir confirmação, nunca cancelar.
"""

from datetime import timedelta

import pytest

from app.risco import calcular, classificar

from .conftest import integracao

pytestmark = integracao

TELEFONE = "+5511911112222"


@pytest.fixture()
def sessao(banco_migrado, org_id):
    """Sessão crua para exercitar o cálculo sem passar pela API."""
    from app.db import SessionLocal, sessao_org

    with SessionLocal() as db:
        sessao_org(db, org_id)
        yield db


def _agendar(client, catalogo, inicio, telefone=TELEFONE):
    return client.post(
        "/appointments",
        json={
            "service_id": catalogo["servico"]["id"],
            "resource_id": catalogo["recurso"]["id"],
            "inicio": inicio,
            "cliente_nome": "Cliente",
            "cliente_telefone": telefone,
        },
    )


def test_faixas_sao_previsiveis():
    assert [classificar(n) for n in (0, 1, 2, 3, 4, 9)] == [
        "baixo", "baixo", "medio", "medio", "alto", "alto",
    ]


def test_a_composicao_do_risco_e_sempre_visivel(client, catalogo):
    corpo = _agendar(client, catalogo, "2027-05-12T14:00:00-03:00").json()
    detalhe = corpo["risco_detalhe"]
    assert detalhe["pontos"] == sum(f["pontos"] for f in detalhe["fatores"])
    assert detalhe["risco"] == corpo["risco_no_show"]
    assert all(f["detalhe"] for f in detalhe["fatores"])  # cada parcela se explica
    assert "sem modelo estatístico" in detalhe["explicacao"]


def test_cliente_novo_aparece_como_primeira_visita(client, catalogo):
    corpo = _agendar(client, catalogo, "2027-05-12T14:00:00-03:00").json()
    fatores = {f["fator"] for f in corpo["risco_detalhe"]["fatores"]}
    assert "primeira_visita" in fatores


def test_faltas_anteriores_levam_a_risco_alto(client, catalogo):
    faltante = "+5511933334444"
    for dia in ("2027-05-12T14:00:00-03:00", "2027-05-13T14:00:00-03:00"):
        ap = _agendar(client, catalogo, dia, telefone=faltante).json()
        assert client.post(f"/appointments/{ap['id']}/no-show").status_code == 200

    novo = _agendar(client, catalogo, "2027-05-14T14:00:00-03:00", telefone=faltante).json()
    assert novo["risco_no_show"] == "alto"
    fatores = {f["fator"]: f["pontos"] for f in novo["risco_detalhe"]["fatores"]}
    assert fatores["faltas_anteriores"] == 4  # 2 faltas × 2 pontos


def test_o_proprio_compromisso_nao_entra_no_seu_historico(client, catalogo):
    """Sem isso, todo agendamento contaria a si mesmo e ninguém seria
    'primeira visita' — o cálculo mediria a própria existência."""
    primeiro = _agendar(client, catalogo, "2027-06-01T14:00:00-03:00").json()
    assert any(
        f["fator"] == "primeira_visita" for f in primeiro["risco_detalhe"]["fatores"]
    )
    segundo = _agendar(client, catalogo, "2027-06-02T14:00:00-03:00").json()
    assert not any(
        f["fator"] == "primeira_visita" for f in segundo["risco_detalhe"]["fatores"]
    )


def test_horario_de_risco_conta_ponto(sessao, org_id):
    from app.tempo import TZ, agora_utc

    base = (agora_utc() + timedelta(days=5)).astimezone(TZ)
    cedo = base.replace(hour=7, minute=0, second=0, microsecond=0)
    comum = base.replace(hour=14, minute=0, second=0, microsecond=0)
    tarde = base.replace(hour=20, minute=0, second=0, microsecond=0)

    def fatores(quando):
        return {f["fator"] for f in calcular(sessao, org_id, "+5511900007777", quando)[1]["fatores"]}

    assert "horario_cedo" in fatores(cedo)
    assert "horario_tarde" in fatores(tarde)
    assert not {"horario_cedo", "horario_tarde"} & fatores(comum)


def test_antecedencia_pesa_nos_dois_extremos(sessao, org_id):
    from app.tempo import agora_utc

    def fatores(delta):
        quando = agora_utc() + delta
        return {f["fator"] for f in calcular(sessao, org_id, "+5511900006666", quando)[1]["fatores"]}

    assert "marcado_em_cima_da_hora" in fatores(timedelta(hours=3))
    assert "marcado_com_muita_antecedencia" in fatores(timedelta(days=60))
    # no meio do caminho, a antecedência não diz nada
    meio = fatores(timedelta(days=5))
    assert not {"marcado_em_cima_da_hora", "marcado_com_muita_antecedencia"} & meio


def test_risco_alto_agenda_lembrete_extra_e_nao_cancela(client, catalogo, org_id):
    """O efeito do risco alto é pedir confirmação — nunca mexer no status."""
    from app.db import SessionLocal, sessao_org
    from app.jobs import agendar_lembrete_de_risco
    from app.models import Appointment, Reminder

    faltante = "+5511955556666"
    for dia in ("2027-07-05T14:00:00-03:00", "2027-07-06T14:00:00-03:00"):
        ap = _agendar(client, catalogo, dia, telefone=faltante).json()
        client.post(f"/appointments/{ap['id']}/no-show")
    alvo = _agendar(client, catalogo, "2027-07-07T14:00:00-03:00", telefone=faltante).json()
    assert alvo["risco_no_show"] == "alto"

    with SessionLocal() as db:
        sessao_org(db, org_id)
        ap = db.get(Appointment, alvo["id"])
        agendar_lembrete_de_risco(db, ap)
        agendar_lembrete_de_risco(db, ap)  # idempotente: não vira enxurrada
        db.commit()
        extras = db.query(Reminder).filter(
            Reminder.appointment_id == ap.id, Reminder.tipo == "risco_alto"
        ).all()
        assert len(extras) == 1
        assert ap.status == "agendado"  # o risco não cancela nada
