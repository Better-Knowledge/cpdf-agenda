# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Linguagem natural de datas — e as recusas, que são metade do valor.

O risco do PRD §16 é "agente interpreta data errada" com probabilidade
**alta**. Metade da mitigação é o `label` por extenso; a outra metade é
levantar `Ambigua` em vez de chutar. Os dois lados estão testados aqui.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.datas import TZ, Ambigua, interpretar

# Uma segunda-feira, 10h da manhã, para todos os testes: sem isso, "quinta que
# vem" mudaria de resposta conforme o dia em que a suíte roda.
AGORA = datetime(2027, 3, 8, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


def i(expressao: str):
    return interpretar(expressao, AGORA)


def test_hoje_e_amanha():
    hoje = i("hoje")
    assert hoje.de.date() == AGORA.date()
    assert i("amanhã").de.date().day == 9
    assert i("depois de amanhã").de.date().day == 10


def test_hoje_nunca_oferece_hora_que_ja_passou():
    """São 10h: 'hoje de manhã' começa agora, não às 6h."""
    manha = i("hoje de manhã")
    assert manha.de == AGORA
    assert manha.ate.hour == 12


def test_periodos_do_dia():
    tarde = i("quinta de tarde")
    assert (tarde.de.hour, tarde.ate.hour) == (12, 18)
    manha = i("quinta de manhã")
    assert (manha.de.hour, manha.ate.hour) == (6, 12)
    noite = i("quinta à noite")
    assert (noite.de.hour, noite.ate.hour) == (18, 22)


def test_dia_da_semana_e_o_proximo():
    quinta = i("quinta")
    assert quinta.de.date() == datetime(2027, 3, 11, tzinfo=TZ).date()
    # hoje é segunda: "segunda" quer dizer a que vem, não hoje
    assert i("segunda").de.date().day == 15


def test_que_vem_pula_a_desta_semana():
    assert i("quinta que vem").de.date().day == 18
    assert i("quinta").de.date().day == 11


def test_semana_que_vem_cobre_a_semana_inteira():
    intervalo = i("semana que vem")
    assert intervalo.de.date().day == 15  # segunda
    assert intervalo.ate.date().day == 21  # domingo
    assert intervalo.label.startswith("de segunda")


def test_fim_de_semana():
    intervalo = i("fim de semana")
    assert intervalo.de.weekday() == 5
    assert intervalo.ate.weekday() == 6


def test_data_explicita_com_barra():
    intervalo = i("12/09")
    assert (intervalo.de.day, intervalo.de.month, intervalo.de.year) == (12, 9, 2027)


def test_o_label_e_por_extenso_para_o_agente_repetir():
    """A mitigação do §16: o agente confirma a data em palavras, não em ISO."""
    assert i("quinta de tarde").label == "quinta, 11 de março, das 12h às 18h"
    assert i("amanhã").label == "terça, 9 de março"


def test_toda_saida_tem_offset():
    intervalo = i("amanhã")
    assert intervalo.de.utcoffset() is not None
    assert "-03:00" in intervalo.como_dict()["de"]


# ── As recusas ───────────────────────────────────────────────────────────────


def test_dia_do_mes_que_ja_passou_vira_pergunta():
    """Hoje é 8/3. 'Dia 5' pode ser abril — ou o cliente se enganou. Chutar
    abril marcaria alguém para o mês errado com toda a confiança do mundo."""
    with pytest.raises(Ambigua) as e:
        i("dia 5")
    assert "já passou" in e.value.pergunta
    assert "abril" in e.value.pergunta


def test_data_com_dia_e_mes_passados_vira_pergunta():
    with pytest.raises(Ambigua) as e:
        i("5/1")
    assert "2028" in e.value.pergunta


def test_dia_do_mes_futuro_e_aceito():
    assert i("dia 20").de.date().day == 20


def test_expressao_desconhecida_pergunta_em_vez_de_falhar():
    with pytest.raises(Ambigua) as e:
        i("quando der")
    assert "Pergunte ao cliente" in e.value.pergunta


def test_data_inexistente_no_calendario():
    with pytest.raises(Ambigua):
        i("31/02")


def test_vazio_pergunta():
    with pytest.raises(Ambigua):
        i("   ")
