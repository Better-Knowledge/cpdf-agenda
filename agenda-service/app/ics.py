"""RF-11 — geração do feed .ics (RFC 5545), função pura e sem banco.

Duas decisões que valem explicação:

**Horário em UTC (`...Z`), não `TZID=America/Sao_Paulo`.** O instante absoluto
é inequívoco em qualquer cliente de calendário, e o app do prestador o exibe
no fuso dele sem que a gente precise embarcar um `VTIMEZONE` — que teria de
ser reescrito no dia em que o horário de verão voltar ao Brasil. O texto que
a pessoa lê (`label_humano`) continua em America/Sao_Paulo.

**O feed é visão, não notificação.** O Google relê calendários assinados em
ciclos de horas; tempo real é papel do push (RF-12) e do canal (RF-05). Esta
expectativa é dita em aula e repetida na descrição do calendário.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from .tempo import label_humano

PRODID = "-//Better Knowledge//Agenda Inteligente//PT-BR"
LIMITE_LINHA = 75  # RFC 5545 §3.1: dobra em 75 octetos


@dataclass(frozen=True)
class Evento:
    uid: str
    inicio: datetime
    fim: datetime
    titulo: str
    descricao: str = ""
    atualizado_em: datetime | None = None


def _escapar(texto: str) -> str:
    """RFC 5545 §3.3.11 — barra, ponto-e-vírgula, vírgula e quebra de linha."""
    return (
        texto.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _carimbo(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _dobrar(linha: str) -> list[str]:
    """Dobra em 75 octetos sem partir caractere multibyte (acento é 2 bytes)."""
    partes: list[str] = []
    atual, tamanho, limite = "", 0, LIMITE_LINHA
    for char in linha:
        octetos = len(char.encode())
        if tamanho + octetos > limite:
            partes.append(atual)
            atual, tamanho, limite = " ", 1, LIMITE_LINHA  # continuação começa com espaço
        atual += char
        tamanho += octetos
    partes.append(atual)
    return partes


def gerar(nome_calendario: str, eventos: list[Evento], agora: datetime) -> str:
    linhas = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escapar(nome_calendario)}",
        "X-WR-TIMEZONE:America/Sao_Paulo",
        # O Google respeita este intervalo como sugestão, não como contrato —
        # daí a expectativa gerenciada em aula.
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    for e in eventos:
        linhas += [
            "BEGIN:VEVENT",
            f"UID:{e.uid}",
            f"DTSTAMP:{_carimbo(e.atualizado_em or agora)}",
            f"DTSTART:{_carimbo(e.inicio)}",
            f"DTEND:{_carimbo(e.fim)}",
            f"SUMMARY:{_escapar(e.titulo)}",
        ]
        if e.descricao:
            linhas.append(f"DESCRIPTION:{_escapar(e.descricao)}")
        linhas.append("END:VEVENT")
    linhas.append("END:VCALENDAR")

    dobradas: list[str] = []
    for linha in linhas:
        dobradas += _dobrar(linha)
    return "\r\n".join(dobradas) + "\r\n"


def titulo_e_descricao(
    *, modo: str, servico: str, cliente: str, status: str, inicio: datetime
) -> tuple[str, str]:
    """No modo privado o feed mostra que o horário está tomado e nada mais.

    Quem assina um feed .ics cola a URL num serviço de terceiros (Google,
    Apple). Se ela vazar, o modo privado limita o estrago a "ocupado das 15h
    às 16h" — sem nome nem telefone de cliente nenhum.
    """
    marca = "" if status != "confirmado" else "✓ "
    if modo == "privado":
        return f"{marca}Ocupado", ""
    return (
        f"{marca}{servico} — {cliente}",
        f"{servico} com {cliente} · {label_humano(inicio)} · status: {status}",
    )
