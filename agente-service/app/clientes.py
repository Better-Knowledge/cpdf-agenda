# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""O agente só existe através das APIs: agenda e canal.

Nunca toca no banco de ninguém, nunca chama a API do WhatsApp direto. Isso
não é purismo: é o que faz o mesmo agente servir o MCP depois sem reescrita.

**A mudança do RF-19.** Até aqui o agente falava com a agenda usando a chave
do serviço e dizia, em cada chamada, para qual organização e telefone estava
trabalhando. Agora ele apresenta o token de sessão que o canal cunhou — e
`org_id` **sai da assinatura** de `agenda()`. Isso não é estética: enquanto
a org viajava por parâmetro, "esquecer de filtrar" era uma classe inteira de
bug possível (a fila de espera vazava assim). Sem o parâmetro, não há o que
esquecer: a autoridade já vem dentro do token, e a agenda filtra na origem.
"""

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx

from .config import settings

log = logging.getLogger("agente.clientes")


class ServicoIndisponivel(Exception):
    pass


@dataclass(frozen=True)
class Sessao:
    """Quem o agente é nesta conversa: uma organização e UM cliente.

    `token` ausente é o modo legado (canal antigo, que ainda não cunha
    sessão): a agenda é chamada com a chave de serviço e o agente volta a
    ter autoridade sobre a organização inteira. É esse caminho que a flag
    ATENDIMENTO_ISOLADO fecha do outro lado.
    """

    org_id: UUID
    telefone: str
    token: str | None = None

    @property
    def isolada(self) -> bool:
        return self.token is not None

    def _cabecalhos_agenda(self) -> dict[str, str]:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        cfg = settings()
        return {"X-Service-Key": cfg.agenda_service_key, "X-Org-Id": str(self.org_id)}


def _chamar(
    base: str, cabecalhos: dict[str, str], metodo: str, rota: str, corpo: Any | None = None
) -> tuple[int, Any]:
    try:
        resposta = httpx.request(
            metodo, f"{base}{rota}", json=corpo, headers=cabecalhos, timeout=20
        )
    except httpx.HTTPError as e:
        raise ServicoIndisponivel(f"{base}{rota}: {e}") from e
    try:
        return resposta.status_code, resposta.json()
    except ValueError:
        return resposta.status_code, {}


def agenda(metodo: str, rota: str, sessao: Sessao, corpo: Any | None = None) -> tuple[int, Any]:
    """Chamada à agenda com a autoridade da conversa — nunca com a do serviço."""
    return _chamar(settings().agenda_service_url, sessao._cabecalhos_agenda(), metodo, rota, corpo)


def canal(metodo: str, rota: str, org_id: UUID, corpo: Any | None = None) -> tuple[int, Any]:
    """O canal continua service-to-service: ele é quem PROVA o endereço, não
    quem o consome. Aplicar aqui o token que ele mesmo emitiu seria circular."""
    cfg = settings()
    return _chamar(
        cfg.canal_service_url,
        {"X-Service-Key": cfg.canal_service_key, "X-Org-Id": str(org_id)},
        metodo,
        rota,
        corpo,
    )


def responder(sessao: Sessao, texto: str) -> None:
    """Resposta dentro da janela de 24h aberta pelo cliente: tipo=sessao.

    O destinatário vem da sessão, não de um parâmetro: o agente responde a
    quem escreveu, e não há caminho para ele mandar mensagem a um terceiro.

    Mensagem ATIVA (lembrete, cobrança) nunca passa por aqui — é template, e
    quem envia é o job da agenda.
    """
    status, corpo = canal(
        "POST",
        "/canal/enviar",
        sessao.org_id,
        {"destinatario": sessao.telefone, "tipo": "sessao", "texto": texto},
    )
    if status >= 400:
        log.warning("canal recusou resposta para %s: %s", sessao.telefone, corpo.get("code"))
