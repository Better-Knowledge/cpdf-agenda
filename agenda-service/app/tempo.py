"""Tempo é invariante do módulo: UTC no banco, America/Sao_Paulo na borda,
datetime naive é proibido. Toda saída de horário: ISO 8601 com offset +
`label_humano` pronto (o agente fala a data sem reformatar — IA-01).
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")

DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def exigir_aware(dt: datetime, campo: str = "data") -> datetime:
    if dt.tzinfo is None:
        from .errors import ApiError

        raise ApiError(
            code="DATA_SEM_FUSO",
            message=f"'{campo}' veio sem offset de fuso horário.",
            hint="Envie ISO 8601 com offset explícito, ex.: 2026-08-27T15:30:00-03:00.",
        )
    return dt


def utc(dt: datetime) -> datetime:
    return exigir_aware(dt).astimezone(UTC)


def local(dt: datetime) -> datetime:
    return exigir_aware(dt).astimezone(TZ)


def label_humano(dt: datetime) -> str:
    """Ex.: "quinta, 14 de maio, 15h30" — sempre no fuso America/Sao_Paulo."""
    d = local(dt)
    hora = f"{d.hour}h{d.minute:02d}" if d.minute else f"{d.hour}h"
    return f"{DIAS_SEMANA[d.weekday()]}, {d.day} de {MESES[d.month - 1]}, {hora}"


def agora_utc() -> datetime:
    return datetime.now(UTC)
