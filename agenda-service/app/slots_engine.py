"""Motor de disponibilidade (RF-02) — função pura, sem banco.

Recebe a grade semanal, bloqueios e ocupações já carregados e devolve os
inícios de slot realmente livres. O cálculo caminha em hora de parede de
America/Sao_Paulo (grade é hora local) e compara em UTC — se o DST voltar
ao Brasil, a conversão por zoneinfo absorve a borda (teste em
tests/test_slots_engine.py).
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from .tempo import TZ, utc


@dataclass(frozen=True)
class RegraGrade:
    dia_semana: int  # 0=segunda … 6=domingo
    hora_inicio: time
    hora_fim: time


Intervalo = tuple[datetime, datetime]  # aware, qualquer fuso


def _conflita(inicio: datetime, fim: datetime, ocupados: list[Intervalo]) -> bool:
    return any(inicio < o_fim and o_inicio < fim for o_inicio, o_fim in ocupados)


def calcular_slots(
    *,
    duracao_min: int,
    buffer_antes_min: int = 0,
    buffer_depois_min: int = 0,
    regras: list[RegraGrade],
    ocupados: list[Intervalo],  # bloqueios + agendamentos + busy externo (RF-12)
    de: datetime,
    ate: datetime,
    agora: datetime,
    granularidade_min: int = 30,
    antecedencia_minima_min: int = 0,
    limite: int = 50,
) -> list[datetime]:
    """Devolve inícios de slot (aware, TZ local), em ordem cronológica."""
    de_l, ate_l = de.astimezone(TZ), ate.astimezone(TZ)
    minimo = agora + timedelta(minutes=antecedencia_minima_min)
    ocupados_utc = [(utc(a), utc(b)) for a, b in ocupados]
    passo = timedelta(minutes=granularidade_min)
    slots: list[datetime] = []

    dia = de_l.date()
    while dia <= ate_l.date() and len(slots) < limite:
        for regra in regras:
            if regra.dia_semana != dia.weekday():
                continue
            janela_ini = datetime.combine(dia, regra.hora_inicio, tzinfo=TZ)
            janela_fim = datetime.combine(dia, regra.hora_fim, tzinfo=TZ)
            candidato = janela_ini
            while candidato + timedelta(minutes=duracao_min) <= janela_fim:
                inicio = candidato
                fim = inicio + timedelta(minutes=duracao_min)
                # A pegada do slot inclui os buffers do serviço…
                pegada_ini = inicio - timedelta(minutes=buffer_antes_min)
                pegada_fim = fim + timedelta(minutes=buffer_depois_min)
                cabe_na_janela = pegada_ini >= janela_ini and pegada_fim <= janela_fim
                if (
                    cabe_na_janela
                    and de <= inicio <= ate
                    and inicio >= minimo
                    and not _conflita(utc(pegada_ini), utc(pegada_fim), ocupados_utc)
                ):
                    slots.append(inicio)
                    if len(slots) >= limite:
                        return slots
                candidato += passo
        dia += timedelta(days=1)
    return slots


def alternativas_proximas(
    slots: list[datetime], alvo: datetime, n: int = 3
) -> list[datetime]:
    """As N opções mais próximas do horário pedido — nunca só 'indisponível' (RF-03)."""
    return sorted(slots, key=lambda s: abs(s - alvo))[:n]
