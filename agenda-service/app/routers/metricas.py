# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""T-10 — os números do §4, calculados onde os dados estão.

A tela poderia somar isto no navegador varrendo `GET /appointments` dia a
dia. Não faz, por dois motivos: seriam dezenas de chamadas para uma tela só,
e a definição de cada métrica ("o que conta como no-show?") acabaria
duplicada entre a UI e qualquer agente que fizesse a mesma pergunta. A
definição mora aqui, uma vez.

Uma convenção que atravessa o arquivo: **denominador zero devolve `None`, não
`0`**. "Não houve compromisso no período" e "todos faltaram" são leituras
opostas, e um zero no lugar do vazio é o jeito clássico de uma métrica
mentir.
"""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.orm import Session

from ..auth import Credencial, credencial_atual, exigir_escopo
from ..contrato import operacao, respostas
from ..db import get_db
from ..models import Appointment, AvailabilityBlock, AvailabilityRule, Resource, WaitlistEntry
from ..schemas import MetricasOut
from ..tempo import TZ, agora_utc

router = APIRouter(tags=["métricas"])

VIVOS = ("agendado", "confirmado", "realizado")


def _pct(parte: float, total: float) -> float | None:
    return None if not total else round(100 * parte / total, 1)


def _horas_de_grade(db: Session, org_id, de: date, ate: date) -> float:
    """Horas de trabalho previstas no período: a grade semanal de cada recurso
    ativo, dia a dia, menos os bloqueios. É o denominador da ocupação — sem
    descontar férias, uma semana de folga apareceria como ociosidade."""
    regras = db.execute(
        select(AvailabilityRule, Resource)
        .join(Resource, Resource.id == AvailabilityRule.resource_id)
        .where(AvailabilityRule.org_id == org_id, Resource.ativo)
    ).all()
    por_recurso: dict = {}
    for regra, _ in regras:
        por_recurso.setdefault(regra.resource_id, []).append(regra)

    horas = 0.0
    dia = de
    while dia <= ate:
        for regras_do_recurso in por_recurso.values():
            for regra in regras_do_recurso:
                if regra.dia_semana == dia.weekday():
                    inicio = datetime.combine(dia, regra.hora_inicio)
                    fim = datetime.combine(dia, regra.hora_fim)
                    horas += (fim - inicio).total_seconds() / 3600
        dia += timedelta(days=1)

    janela = Range(
        datetime.combine(de, datetime.min.time(), tzinfo=TZ),
        datetime.combine(ate + timedelta(days=1), datetime.min.time(), tzinfo=TZ),
    )
    for bloco in db.scalars(
        select(AvailabilityBlock).where(
            AvailabilityBlock.org_id == org_id, AvailabilityBlock.periodo.overlaps(janela)
        )
    ):
        inicio = max(bloco.periodo.lower, janela.lower)
        fim = min(bloco.periodo.upper, janela.upper)
        horas -= max(0.0, (fim - inicio).total_seconds() / 3600)
    return max(0.0, horas)


@router.get(
    "/metricas",
    response_model=MetricasOut,
    summary="Os números da operação num período",
    description=(
        "Ocupação, faltas, confirmações e de onde vieram os agendamentos (conversa, "
        "link público, Calendly, humano) — as métricas do PRD §4. Percentual com "
        "denominador zero volta `null`, não `0`. Exige `agenda:operacao`: são dados "
        "da agenda inteira."
    ),
    responses=respostas(),
    openapi_extra=operacao("agenda:operacao"),
)
def metricas(
    de: date = Query(description="Primeiro dia do período (inclusive)"),
    ate: date = Query(description="Último dia do período (inclusive)"),
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> MetricasOut:
    exigir_escopo(cred, "agenda:operacao")
    inicio = datetime.combine(de, datetime.min.time(), tzinfo=TZ)
    fim = datetime.combine(ate + timedelta(days=1), datetime.min.time(), tzinfo=TZ)
    janela = Range(inicio, fim)

    compromissos = list(
        db.scalars(
            select(Appointment).where(
                Appointment.org_id == cred.org_id, Appointment.periodo.overlaps(janela)
            )
        )
    )
    total = len(compromissos)
    por_status: dict[str, int] = {}
    por_origem: dict[str, int] = {}
    for ap in compromissos:
        por_status[ap.status] = por_status.get(ap.status, 0) + 1
        por_origem[ap.origem] = por_origem.get(ap.origem, 0) + 1

    agora = agora_utc()
    # No-show só faz sentido sobre o que já aconteceu: contar o futuro no
    # denominador faria a taxa cair sozinha à medida que a agenda enche.
    passados = [ap for ap in compromissos if ap.periodo.upper <= agora and ap.status != "cancelado"]
    faltas = [ap for ap in passados if ap.status == "no_show"]

    horas_agendadas = sum(
        (ap.periodo.upper - ap.periodo.lower).total_seconds() / 3600
        for ap in compromissos
        if ap.status in VIVOS
    )
    horas_grade = _horas_de_grade(db, cred.org_id, de, ate)

    fila_aguardando = db.scalar(
        select(func.count())
        .select_from(WaitlistEntry)
        .where(WaitlistEntry.org_id == cred.org_id, WaitlistEntry.status.in_(("aguardando", "ofertado")))
    )
    fila_atendida = db.scalar(
        select(func.count())
        .select_from(WaitlistEntry)
        .where(WaitlistEntry.org_id == cred.org_id, WaitlistEntry.status == "aceito")
    )

    pct_conversa = _pct(por_origem.get("agente", 0), total)
    pct_no_show = _pct(len(faltas), len(passados))
    pct_confirmados = _pct(por_status.get("confirmado", 0) + por_status.get("realizado", 0), total)
    pct_ocupacao = _pct(horas_agendadas, horas_grade)

    partes = [f"{total} compromissos entre {de:%d/%m} e {ate:%d/%m}"]
    if pct_conversa is not None:
        partes.append(f"{pct_conversa}% vieram por conversa")
    if pct_ocupacao is not None:
        partes.append(f"ocupação de {pct_ocupacao}% da grade")
    if pct_no_show is not None:
        partes.append(f"{pct_no_show}% de faltas no que já passou")
    if por_status.get("cancelado"):
        partes.append(f"{por_status['cancelado']} cancelados")

    return MetricasOut(
        de=de,
        ate=ate,
        total=total,
        por_status=por_status,
        por_origem=por_origem,
        pct_por_conversa=pct_conversa,
        pct_no_show=pct_no_show,
        pct_confirmados=pct_confirmados,
        pct_ocupacao=pct_ocupacao,
        cancelados=por_status.get("cancelado", 0),
        fila_aguardando=fila_aguardando or 0,
        fila_atendida=fila_atendida or 0,
        narrativa=" · ".join(partes) + ".",
    )
