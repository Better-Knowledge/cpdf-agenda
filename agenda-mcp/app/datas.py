# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Linguagem natural de datas — e o que ela se recusa a adivinhar.

O cliente escreve "quinta de tarde", "semana que vem", "dia 12". O agente
precisa disso como um intervalo ISO com offset para chamar a agenda. Este
módulo faz a conversão, é puro (recebe o `agora`) e vive no conector porque
é interpretação de conversa, não regra de negócio.

**A parte mais importante é a recusa.** O risco registrado no PRD §16 é
"agente interpreta data errada", e a mitigação combinada do programa tem duas
metades: repetir a data por extenso antes de confirmar, e **não chutar**. Por
isso toda expressão que admite mais de uma leitura levanta `Ambigua`, com a
pergunta pronta para o agente devolver ao cliente. Um `label` por extenso
acompanha todo intervalo interpretado, exatamente para a primeira metade.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")

DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]
_DIAS_SEM_ACENTO = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
_MESES_SEM_ACENTO = [
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

# Faixas de hora dos períodos do dia, em hora de parede.
PERIODOS: dict[str, tuple[time, time]] = {
    "manha": (time(6), time(12)),
    "tarde": (time(12), time(18)),
    "noite": (time(18), time(22)),
}
DIA_INTEIRO = (time(0), time(23, 59))


@dataclass(frozen=True)
class Intervalo:
    de: datetime
    ate: datetime
    label: str

    def como_dict(self) -> dict[str, str]:
        return {"de": self.de.isoformat(), "ate": self.ate.isoformat(), "label": self.label}


class Ambigua(Exception):
    """A expressão admite mais de uma leitura — pergunte, não adivinhe.

    `pergunta` é escrita para o agente mandar ao cliente sem reescrever.
    """

    def __init__(self, pergunta: str):
        self.pergunta = pergunta
        super().__init__(pergunta)


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower().strip()


def _por_extenso(d: date) -> str:
    return f"{DIAS[d.weekday()]}, {d.day} de {MESES[d.month - 1]}"


def _label(inicio: datetime, fim: datetime) -> str:
    """O texto que o agente repete ao cliente antes de confirmar."""
    if inicio.date() == fim.date():
        dia = _por_extenso(inicio.date())
        if (inicio.time(), fim.time()) == DIA_INTEIRO:
            return dia
        return f"{dia}, das {inicio.hour}h às {fim.hour}h"
    return f"de {_por_extenso(inicio.date())} a {_por_extenso(fim.date())}"


def _montar(dia_inicio: date, dia_fim: date, faixa: tuple[time, time], agora: datetime) -> Intervalo:
    inicio = datetime.combine(dia_inicio, faixa[0], tzinfo=TZ)
    fim = datetime.combine(dia_fim, faixa[1], tzinfo=TZ)
    # Pedir "hoje de manhã" às 11h não deve oferecer as 8h que já passaram.
    inicio = max(inicio, agora.astimezone(TZ))
    return Intervalo(inicio, fim, _label(datetime.combine(dia_inicio, faixa[0], tzinfo=TZ), fim))


def _periodo(texto: str) -> tuple[time, time]:
    """Com fronteira de palavra: sem ela, "amanha" contém "manha" e todo
    "amanhã" viraria "amanhã de manhã" — um erro que só apareceria quando o
    cliente perdesse o horário da tarde que tinha pedido."""
    if re.search(r"\b(manha|cedo)\b", texto):
        return PERIODOS["manha"]
    if re.search(r"\btarde\b", texto):
        return PERIODOS["tarde"]
    if re.search(r"\bnoite\b", texto):
        return PERIODOS["noite"]
    return DIA_INTEIRO


def _proximo_dia_da_semana(hoje: date, alvo: int, semana_que_vem: bool) -> date:
    """"Quinta" é a próxima quinta; "quinta que vem" pula a desta semana.

    Quando hoje **é** o dia citado, a leitura corrente em português é "hoje
    não, o próximo" — quem quer hoje diz "hoje".
    """
    dias = (alvo - hoje.weekday()) % 7 or 7
    if semana_que_vem:
        dias += 7 if dias <= (6 - hoje.weekday()) else 0
    return hoje + timedelta(days=dias)


_DIA_MES = re.compile(r"\b(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{2,4}))?\b")
_DIA_DE_MES = re.compile(r"\bdia\s+(\d{1,2})\s+de\s+([a-z]+)\b")
_SO_DIA = re.compile(r"\bdia\s+(\d{1,2})\b")
_PROXIMOS_N = re.compile(r"\bpr[oó]ximos?\s+(\d{1,2})\s+dias\b")


def interpretar(expressao: str, agora: datetime) -> Intervalo:
    """Expressão em português → intervalo com offset. Levanta `Ambigua`."""
    texto = _sem_acento(expressao)
    if not texto:
        raise Ambigua("Para qual dia? Pode ser 'amanhã', 'quinta de tarde' ou uma data.")
    hoje = agora.astimezone(TZ).date()
    faixa = _periodo(texto)
    semana_que_vem = any(p in texto for p in ("que vem", "proxima", "proximo", "seguinte"))

    if "depois de amanha" in texto:
        return _montar(hoje + timedelta(days=2), hoje + timedelta(days=2), faixa, agora)
    if "amanha" in texto:
        return _montar(hoje + timedelta(days=1), hoje + timedelta(days=1), faixa, agora)
    if "hoje" in texto or "ainda hoje" in texto:
        return _montar(hoje, hoje, faixa, agora)

    if "fim de semana" in texto or "final de semana" in texto:
        sabado = _proximo_dia_da_semana(hoje, 5, semana_que_vem=False)
        return _montar(sabado, sabado + timedelta(days=1), faixa, agora)

    if "semana" in texto and semana_que_vem:
        segunda = _proximo_dia_da_semana(hoje, 0, semana_que_vem=False)
        return _montar(segunda, segunda + timedelta(days=6), faixa, agora)
    if "esta semana" in texto or "essa semana" in texto:
        return _montar(hoje, hoje + timedelta(days=6 - hoje.weekday()), faixa, agora)

    if m := _PROXIMOS_N.search(texto):
        return _montar(hoje, hoje + timedelta(days=int(m.group(1))), faixa, agora)
    if "proximos dias" in texto:
        return _montar(hoje, hoje + timedelta(days=7), faixa, agora)

    for indice, nome in enumerate(_DIAS_SEM_ACENTO):
        if re.search(rf"\b{nome}\b", texto):
            dia = _proximo_dia_da_semana(hoje, indice, semana_que_vem)
            return _montar(dia, dia, faixa, agora)

    if m := _DIA_DE_MES.search(texto):
        numero, mes_nome = int(m.group(1)), m.group(2)
        if mes_nome not in _MESES_SEM_ACENTO:
            raise Ambigua(f"Não reconheci o mês '{mes_nome}'. Qual é a data, no formato dia/mês?")
        mes = _MESES_SEM_ACENTO.index(mes_nome) + 1
        return _data_explicita(numero, mes, None, hoje, faixa, agora)

    if m := _DIA_MES.search(texto):
        ano = int(m.group(3)) if m.group(3) else None
        if ano and ano < 100:
            ano += 2000
        return _data_explicita(int(m.group(1)), int(m.group(2)), ano, hoje, faixa, agora)

    if m := _SO_DIA.search(texto):
        return _dia_do_mes(int(m.group(1)), hoje, faixa, agora)

    raise Ambigua(
        f"Não entendi \"{expressao.strip()}\" como uma data. Pergunte ao cliente o dia — "
        "'amanhã', 'quinta de tarde' ou uma data como 12/09 servem."
    )


def _data_explicita(
    dia: int, mes: int, ano: int | None, hoje: date, faixa: tuple[time, time], agora: datetime
) -> Intervalo:
    try:
        alvo = date(ano or hoje.year, mes, dia)
    except ValueError as e:
        raise Ambigua(f"{dia}/{mes} não existe no calendário. Confirme a data com o cliente.") from e
    if ano is None and alvo < hoje:
        # Dia e mês sem ano, já passados: "5/1" em agosto é janeiro que vem.
        # Trocar o ano em silêncio é justamente o tipo de chute que o §16 pede
        # para não dar.
        raise Ambigua(
            f"{dia}/{mes} já passou este ano. O cliente quer dizer {dia}/{mes}/{hoje.year + 1}?"
        )
    return _montar(alvo, alvo, faixa, agora)


def _dia_do_mes(dia: int, hoje: date, faixa: tuple[time, time], agora: datetime) -> Intervalo:
    """"Dia 12" sem mês: deste mês se ainda não passou; senão, é pergunta."""
    try:
        deste_mes = date(hoje.year, hoje.month, dia)
    except ValueError as e:
        raise Ambigua(f"Não existe dia {dia} neste mês. Qual é a data?") from e
    if deste_mes >= hoje:
        return _montar(deste_mes, deste_mes, faixa, agora)
    seguinte = (hoje.replace(day=1) + timedelta(days=32)).replace(day=1)
    raise Ambigua(
        f"O dia {dia} deste mês já passou. O cliente quer dia {dia} de "
        f"{MESES[seguinte.month - 1]}?"
    )
