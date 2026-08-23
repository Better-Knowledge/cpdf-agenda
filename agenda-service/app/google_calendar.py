# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""RF-12 — Google Calendar: push de eventos + busy-read.

O que este módulo NÃO faz, de propósito:

- **Não decide nada de negócio.** Ele fala HTTP com o Google e traduz falha
  em duas exceções: `GoogleIndisponivel` (rede, 5xx, quota — repetir adianta)
  e `GoogleRecusou` (4xx — repetir não adianta). Quem decide o que fazer com
  isso é o job de push e o motor de slots.
- **Não bloqueia agendamento.** Critério do RF-12: o Google fora do ar não
  pode impedir que um cliente marque horário. O push é assíncrono e o
  busy-read degrada para o cálculo local com aviso no log.
- **Não escreve na agenda.** A sincronização é one-way nesta fase; o evento
  pushado leva na descrição o aviso "gerencie pela agenda". Bidirecional
  (arrastar o evento no Google e refletir aqui) exige webhook + sync token e
  está no roadmap (§18).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx

from .config import settings
from .tempo import agora_utc, label_humano

log = logging.getLogger("agenda.google")

AUTORIZACAO_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOGACAO_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/calendar/v3"

# Escopo mínimo (RF-12): escrever os próprios eventos e ler livre/ocupado.
# `calendar` (leitura completa da agenda alheia) seria pedir demais para o que
# o produto faz.
ESCOPOS = (
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.freebusy",
)

TIMEOUT = 15
# O busy-read roda dentro do GET /slots, que o cliente está esperando. Melhor
# calcular só com os dados locais do que segurar a conversa por 15 s.
TIMEOUT_BUSY = 5
MARGEM_RENOVACAO = timedelta(minutes=5)

AVISO_NO_EVENTO = (
    "Criado pela Agenda Inteligente — gerencie por lá (remarcar ou cancelar aqui "
    "no Google não volta para a agenda)."
)


class GoogleIndisponivel(Exception):
    """Falha transitória: rede, timeout, 5xx, quota. Retry adianta."""


class GoogleRecusou(Exception):
    """4xx: token revogado, calendário inexistente, escopo insuficiente."""


def configurado() -> bool:
    cfg = settings()
    return bool(cfg.google_client_id and cfg.google_client_secret)


def _pedir(metodo: str, url: str, *, timeout: float = TIMEOUT, **kw) -> dict:
    try:
        resposta = httpx.request(metodo, url, timeout=timeout, **kw)
    except httpx.HTTPError as e:
        raise GoogleIndisponivel(str(e)) from e
    if resposta.status_code >= 500 or resposta.status_code == 429:
        raise GoogleIndisponivel(f"Google respondeu {resposta.status_code}")
    if resposta.status_code >= 400:
        raise GoogleRecusou(f"{resposta.status_code}: {resposta.text[:200]}")
    return resposta.json() if resposta.content else {}


# ── OAuth ────────────────────────────────────────────────────────────────────


def url_de_autorizacao(*, state: str, redirect_uri: str) -> str:
    """`access_type=offline` + `prompt=consent` para garantir o refresh_token:
    sem ele, a conexão morre em uma hora e o prestador reconecta na mão."""
    return AUTORIZACAO_URL + "?" + urlencode(
        {
            "client_id": settings().google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(ESCOPOS),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
    )


def trocar_codigo(codigo: str, redirect_uri: str) -> dict:
    cfg = settings()
    return _pedir(
        "POST",
        TOKEN_URL,
        data={
            "code": codigo,
            "client_id": cfg.google_client_id,
            "client_secret": cfg.google_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )


def renovar(refresh_token: str) -> dict:
    cfg = settings()
    return _pedir(
        "POST",
        TOKEN_URL,
        data={
            "refresh_token": refresh_token,
            "client_id": cfg.google_client_id,
            "client_secret": cfg.google_client_secret,
            "grant_type": "refresh_token",
        },
    )


def revogar(token: str) -> None:
    """Desconectar revoga de verdade no Google, não só apaga daqui (RF-12).

    Falha do Google não impede a desconexão local: o pior caso é um token
    órfão que expira sozinho, e manter a linha aqui seria pior.
    """
    try:
        _pedir("POST", REVOGACAO_URL, data={"token": token})
    except (GoogleIndisponivel, GoogleRecusou) as e:
        log.warning("revogação no Google falhou (seguimos apagando aqui): %s", e)


@dataclass(frozen=True)
class Credenciais:
    access_token: str
    refresh_token: str
    expira_em: datetime

    @property
    def vencido(self) -> bool:
        return agora_utc() + MARGEM_RENOVACAO >= self.expira_em

    def como_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expira_em": self.expira_em.isoformat(),
        }

    @classmethod
    def de_resposta(cls, dados: dict, refresh_token: str = "") -> "Credenciais":
        return cls(
            access_token=dados["access_token"],
            # A renovação não repete o refresh_token — quem o perde perde a conexão.
            refresh_token=dados.get("refresh_token") or refresh_token,
            expira_em=agora_utc() + timedelta(seconds=int(dados.get("expires_in", 3600))),
        )

    @classmethod
    def de_dict(cls, dados: dict) -> "Credenciais":
        return cls(
            access_token=dados["access_token"],
            refresh_token=dados["refresh_token"],
            expira_em=datetime.fromisoformat(dados["expira_em"]),
        )


# ── Eventos (push) ───────────────────────────────────────────────────────────


def _cabecalhos(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def corpo_do_evento(
    *, titulo: str, inicio: datetime, fim: datetime, descricao: str = ""
) -> dict:
    return {
        "summary": titulo,
        "description": (descricao + "\n\n" if descricao else "") + AVISO_NO_EVENTO,
        "start": {"dateTime": inicio.isoformat(), "timeZone": "America/Sao_Paulo"},
        "end": {"dateTime": fim.isoformat(), "timeZone": "America/Sao_Paulo"},
        "source": {"title": "Agenda Inteligente", "url": "https://better-knowledge.com"},
    }


def criar_evento(access_token: str, calendar_id: str, evento: dict) -> str:
    dados = _pedir(
        "POST", f"{API}/calendars/{calendar_id}/events", headers=_cabecalhos(access_token),
        json=evento,
    )
    return dados["id"]


def atualizar_evento(access_token: str, calendar_id: str, event_id: str, evento: dict) -> None:
    _pedir(
        "PATCH", f"{API}/calendars/{calendar_id}/events/{event_id}",
        headers=_cabecalhos(access_token), json=evento,
    )


def remover_evento(access_token: str, calendar_id: str, event_id: str) -> None:
    try:
        _pedir(
            "DELETE", f"{API}/calendars/{calendar_id}/events/{event_id}",
            headers=_cabecalhos(access_token),
        )
    except GoogleRecusou as e:
        # 404/410: o evento já não existe lá. O efeito desejado é o estado
        # final, e ele já vale — insistir seria transformar sucesso em erro.
        if "404" not in str(e) and "410" not in str(e):
            raise


def livre_ocupado(
    access_token: str, calendar_id: str, de: datetime, ate: datetime
) -> list[tuple[datetime, datetime]]:
    dados = _pedir(
        "POST", f"{API}/freeBusy", headers=_cabecalhos(access_token), timeout=TIMEOUT_BUSY,
        json={
            "timeMin": de.isoformat(),
            "timeMax": ate.isoformat(),
            "items": [{"id": calendar_id}],
        },
    )
    calendario = dados.get("calendars", {}).get(calendar_id, {})
    if erros := calendario.get("errors"):
        raise GoogleRecusou(f"freeBusy: {erros}")
    return [
        (datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"]))
        for b in calendario.get("busy", [])
    ]


def titulo_do_compromisso(servico: str, cliente: str) -> str:
    return f"{servico} — {cliente}"


def descricao_do_compromisso(*, cliente: str, telefone: str, inicio: datetime) -> str:
    return f"Cliente: {cliente} ({telefone})\nHorário combinado: {label_humano(inicio)}"
