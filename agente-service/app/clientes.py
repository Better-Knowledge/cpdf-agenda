"""O agente só existe através das APIs: agenda e canal.

Nunca toca no banco de ninguém, nunca chama a API do WhatsApp direto. Isso
não é purismo: é o que faz o mesmo agente servir o MCP depois sem reescrita.
"""

import logging
from typing import Any
from uuid import UUID

import httpx

from .config import settings

log = logging.getLogger("agente.clientes")


class ServicoIndisponivel(Exception):
    pass


def _chamar(
    base: str, chave: str, metodo: str, rota: str, org_id: UUID, corpo: Any | None = None
) -> tuple[int, Any]:
    try:
        resposta = httpx.request(
            metodo,
            f"{base}{rota}",
            json=corpo,
            headers={"X-Service-Key": chave, "X-Org-Id": str(org_id)},
            timeout=20,
        )
    except httpx.HTTPError as e:
        raise ServicoIndisponivel(f"{base}{rota}: {e}") from e
    try:
        return resposta.status_code, resposta.json()
    except ValueError:
        return resposta.status_code, {}


def agenda(metodo: str, rota: str, org_id: UUID, corpo: Any | None = None) -> tuple[int, Any]:
    cfg = settings()
    return _chamar(cfg.agenda_service_url, cfg.agenda_service_key, metodo, rota, org_id, corpo)


def canal(metodo: str, rota: str, org_id: UUID, corpo: Any | None = None) -> tuple[int, Any]:
    cfg = settings()
    return _chamar(cfg.canal_service_url, cfg.canal_service_key, metodo, rota, org_id, corpo)


def responder(org_id: UUID, telefone: str, texto: str) -> None:
    """Resposta dentro da janela de 24h aberta pelo cliente: tipo=sessao.

    Mensagem ATIVA (lembrete, cobrança) nunca passa por aqui — é template, e
    quem envia é o job da agenda.
    """
    status, corpo = canal(
        "POST", "/canal/enviar", org_id, {"destinatario": telefone, "tipo": "sessao", "texto": texto}
    )
    if status >= 400:
        log.warning("canal recusou resposta para %s: %s", telefone, corpo.get("code"))
