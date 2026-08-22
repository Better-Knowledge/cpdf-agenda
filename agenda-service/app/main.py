"""agenda-service — Agenda Inteligente (módulo 02 do AS/IA Avançado).

API-first: este OpenAPI é o contrato que a UI, o link público e o
`agenda-mcp` consomem (RF-17). As descrições das rotas são prescritivas de
propósito — o mesmo texto alimenta as descrições das tools MCP.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from scalar_fastapi import get_scalar_api_reference

from .config import settings
from .errors import instalar_handlers
from .jobs import criar_scheduler
from .routers import appointments, availability, health, resources, services, slots

logging.basicConfig(level=settings().log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = criar_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Agenda Inteligente — agenda-service",
    version="0.1.0",
    description=(
        "Agendamento operado por conversa: slots, agendamento sem double-booking "
        "(garantido no banco), lembretes via canal de WhatsApp. Erros seguem "
        "`{code, message, hint, retryable}` — o hint é escrito para o agente agir. "
        "Escopos: `agenda:read`, `agenda:write`, `agenda:cancel`."
    ),
    docs_url=None,  # /docs é o Scalar (RF-17)
    redoc_url=None,
    lifespan=lifespan,
)

instalar_handlers(app)
app.include_router(health.router)
app.include_router(services.router)
app.include_router(resources.router)
app.include_router(availability.router)
app.include_router(slots.router)
app.include_router(appointments.router)


@app.get("/docs", include_in_schema=False)
async def scalar_docs():
    return get_scalar_api_reference(openapi_url=app.openapi_url, title=app.title)
