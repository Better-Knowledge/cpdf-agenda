# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

from datetime import datetime, time, timedelta

from app.slots_engine import RegraGrade, alternativas_proximas, calcular_slots
from app.tempo import TZ

# 2026-08-27 é uma quinta-feira
QUINTA = datetime(2026, 8, 27, 0, 0, tzinfo=TZ)
GRADE_QUINTA = [RegraGrade(dia_semana=3, hora_inicio=time(9), hora_fim=time(12))]


def _slots(**kw):
    padrao = dict(
        duracao_min=60,
        regras=GRADE_QUINTA,
        ocupados=[],
        de=QUINTA,
        ate=QUINTA + timedelta(days=1),
        agora=QUINTA - timedelta(days=7),
        granularidade_min=30,
    )
    return calcular_slots(**{**padrao, **kw})


def test_grade_simples_respeita_duracao_e_granularidade():
    slots = _slots()
    horas = [(s.hour, s.minute) for s in slots]
    assert horas == [(9, 0), (9, 30), (10, 0), (10, 30), (11, 0)]  # 11h30+60min estoura 12h


def test_ocupacao_remove_slots_que_conflitam():
    ocupado = (
        QUINTA.replace(hour=10),
        QUINTA.replace(hour=11),
    )
    horas = [(s.hour, s.minute) for s in _slots(ocupados=[ocupado])]
    assert horas == [(9, 0), (11, 0)]


def test_buffers_consomem_a_janela():
    # buffer_depois de 30: último início possível recua meia hora
    horas = [(s.hour, s.minute) for s in _slots(buffer_depois_min=30)]
    assert horas == [(9, 0), (9, 30), (10, 0), (10, 30)]


def test_antecedencia_minima_corta_o_passado_proximo():
    agora = QUINTA.replace(hour=9, minute=45)
    horas = [(s.hour, s.minute) for s in _slots(agora=agora, antecedencia_minima_min=60)]
    assert horas == [(11, 0)]  # 10h45 é o mínimo; próximo passo de grade é 11h


def test_alternativas_sao_as_mais_proximas_do_alvo():
    slots = _slots()
    alvo = QUINTA.replace(hour=10, minute=15)
    alternativas = alternativas_proximas(slots, alvo, n=3)
    assert [(s.hour, s.minute) for s in alternativas] == [(10, 0), (10, 30), (9, 30)]


def test_borda_de_horario_de_verao_nao_gera_slot_fantasma():
    """Em 2018-11-04 o Brasil adiantou o relógio (meia-noite → 1h).

    A grade é hora de parede: os slots continuam 9h–12h locais, sem buraco
    nem duplicata, e a conversão UTC absorve o offset que mudou de -03 → -02.
    """
    domingo_dst = datetime(2018, 11, 4, 0, 0, tzinfo=TZ)
    slots = calcular_slots(
        duracao_min=60,
        regras=[RegraGrade(dia_semana=6, hora_inicio=time(9), hora_fim=time(12))],
        ocupados=[],
        de=domingo_dst,
        ate=domingo_dst + timedelta(days=1),
        agora=domingo_dst - timedelta(days=7),
        granularidade_min=60,
    )
    assert [(s.hour, s.minute) for s in slots] == [(9, 0), (10, 0), (11, 0)]
    assert len(set(slots)) == len(slots)
    assert all(s.utcoffset() == timedelta(hours=-2) for s in slots)  # offset de DST
