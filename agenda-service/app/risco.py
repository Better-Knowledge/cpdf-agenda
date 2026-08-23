# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""IA-03 — risco de no-show, determinístico e explicável.

Sem ML de propósito (PRD §8): com poucas dezenas de agendamentos por
organização, um modelo aprenderia ruído e a gente não saberia dizer por quê.
Pontos somados por fatores observáveis, com a composição sempre visível — o
prestador consegue discordar do número olhando as parcelas.

Efeito do risco alto: um lembrete EXTRA pedindo confirmação explícita.
Nunca cancela nada sozinho.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Appointment
from .tempo import TZ, agora_utc

# Faixas: a soma dos pontos vira uma palavra que cabe numa conversa.
LIMITE_ALTO = 4
LIMITE_MEDIO = 2

PESO_FALTA = 2
MAXIMO_POR_FALTAS = 4


def _fatores(
    db: Session,
    org_id: uuid.UUID,
    telefone: str,
    inicio: datetime,
    ignorar_id: uuid.UUID | None = None,
) -> list[dict]:
    """Cada fator vira uma linha com pontos e explicação em português."""
    anteriores = select(Appointment).where(
        Appointment.org_id == org_id, Appointment.cliente_telefone == telefone
    )
    if ignorar_id is not None:
        anteriores = anteriores.where(Appointment.id != ignorar_id)

    faltas = db.scalar(
        select(func.count()).select_from(anteriores.where(Appointment.status == "no_show").subquery())
    )
    total_anteriores = db.scalar(select(func.count()).select_from(anteriores.subquery()))

    fatores: list[dict] = []

    if faltas:
        pontos = min(faltas * PESO_FALTA, MAXIMO_POR_FALTAS)
        fatores.append(
            {
                "fator": "faltas_anteriores",
                "pontos": pontos,
                "detalhe": f"{faltas} falta(s) registrada(s) antes",
            }
        )

    if total_anteriores == 0:
        fatores.append(
            {
                "fator": "primeira_visita",
                "pontos": 1,
                "detalhe": "primeiro agendamento deste cliente",
            }
        )

    antecedencia = inicio - agora_utc()
    if antecedencia < timedelta(hours=24):
        fatores.append(
            {
                "fator": "marcado_em_cima_da_hora",
                "pontos": 1,
                "detalhe": "marcado com menos de 24h de antecedência",
            }
        )
    elif antecedencia > timedelta(days=30):
        fatores.append(
            {
                "fator": "marcado_com_muita_antecedencia",
                "pontos": 1,
                "detalhe": "marcado com mais de 30 dias — dá tempo de esquecer",
            }
        )

    hora_local = inicio.astimezone(TZ).hour
    if hora_local < 9:
        fatores.append(
            {"fator": "horario_cedo", "pontos": 1, "detalhe": "antes das 9h"}
        )
    elif hora_local >= 19:
        fatores.append(
            {"fator": "horario_tarde", "pontos": 1, "detalhe": "depois das 19h"}
        )

    return fatores


def classificar(pontos: int) -> str:
    if pontos >= LIMITE_ALTO:
        return "alto"
    if pontos >= LIMITE_MEDIO:
        return "medio"
    return "baixo"


def calcular(
    db: Session,
    org_id: uuid.UUID,
    telefone: str,
    inicio: datetime,
    ignorar_id: uuid.UUID | None = None,
) -> tuple[str, dict]:
    """Devolve (risco, composição). A composição vai para `risco_detalhe`
    e é o que a UI e o agente mostram quando alguém pergunta 'por quê?'."""
    fatores = _fatores(db, org_id, telefone, inicio, ignorar_id)
    pontos = sum(f["pontos"] for f in fatores)
    risco = classificar(pontos)
    return risco, {
        "pontos": pontos,
        "risco": risco,
        "fatores": fatores,
        "calculado_em": agora_utc().isoformat(),
        "explicacao": (
            "Soma de pontos por fatores observáveis — sem modelo estatístico. "
            f"{pontos} ponto(s): {classificar(pontos)}."
        ),
    }


def aplicar(db: Session, ap: Appointment) -> str:
    """Calcula e grava no compromisso. Ignora o próprio no histórico."""
    risco, detalhe = calcular(
        db, ap.org_id, ap.cliente_telefone, ap.periodo.lower, ignorar_id=ap.id
    )
    ap.risco_no_show = risco
    ap.risco_detalhe = detalhe
    return risco
