"""ASGI do conector: Streamable HTTP em `/mcp`.

O transporte HTTP+SSE antigo está depreciado (`00` §5) e não é servido aqui.
"""

import logging
from contextlib import asynccontextmanager

from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import agenda
from .config import settings
from .servidor import mcp

logging.basicConfig(level=settings().log_level)
log = logging.getLogger("agenda_admin_mcp")


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "servidor": "agenda-admin", "tools": 11})


def _seguranca_de_transporte() -> TransportSecuritySettings:
    """Proteção contra DNS rebinding: um site qualquer aberto no navegador do
    operador não pode fazer o browser dele falar com este endpoint.

    O SDK liga a proteção por padrão e valida o Host contra uma lista — que,
    vazia, recusa tudo. Por isso a escolha aqui é explícita nos dois sentidos:
    em produção, sem a lista o serviço **não sobe** (melhor do que subir e
    responder 421 a cada chamada, que pareceria bug de rede); em
    desenvolvimento, desliga com aviso.
    """
    cfg = settings()
    if cfg.mcp_hosts_permitidos:
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=cfg.mcp_hosts_permitidos,
            allowed_origins=[f"https://{h}" for h in cfg.mcp_hosts_permitidos],
        )
    if not cfg.dev_mode:
        raise RuntimeError(
            "MCP_HOSTS_PERMITIDOS vazio em produção: informe o domínio público do "
            "conector (ex.: MCP_HOSTS_PERMITIDOS='[\"mcp.suaempresa.com\"]')."
        )
    log.warning("MCP_HOSTS_PERMITIDOS vazio — proteção de DNS rebinding desligada (dev)")
    return TransportSecuritySettings(enable_dns_rebinding_protection=False)


def criar_app():
    aplicacao = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        transport_security=_seguranca_de_transporte(),
    )
    # O app do SDK já traz o lifespan do session manager; embrulhar em vez de
    # substituir mantém aquele funcionando e ainda fecha o cliente HTTP.
    interno = aplicacao.router.lifespan_context

    @asynccontextmanager
    async def lifespan(escopo):
        async with interno(escopo):
            try:
                yield
            finally:
                await agenda.fechar()

    aplicacao.router.lifespan_context = lifespan
    return aplicacao


app = criar_app()
