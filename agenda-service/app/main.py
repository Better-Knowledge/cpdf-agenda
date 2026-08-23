"""agenda-service — Agenda Inteligente (módulo 02 do AS/IA Avançado).

API-first: este OpenAPI é o contrato que a UI, o link público e o
`agenda-mcp` consomem (RF-17). As descrições das rotas são prescritivas de
propósito — o mesmo texto alimenta as descrições das tools MCP. O critério
de aceite: dá para executar um agendamento completo lendo só o /docs.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from scalar_fastapi import get_scalar_api_reference

from .config import settings
from .errors import instalar_handlers
from .jobs import criar_scheduler
from .routers import (
    appointments,
    availability,
    health,
    recorrencia,
    resources,
    services,
    slots,
)

logging.basicConfig(level=settings().log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = criar_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


DESCRICAO = """\
Agendamento operado por conversa: slots, agendamento sem double-booking
(garantido no banco), lembretes via canal de WhatsApp.

## Como usar (o fluxo completo em 4 chamadas)

1. `GET /services` — descubra o `service_id` do que o cliente quer;
2. `GET /slots?service_id=…&from=…&to=…` — horários realmente livres;
3. `POST /appointments` — agende com nome + telefone do cliente;
4. Deu 409 `SLOT_INDISPONIVEL`? As 3 alternativas já vêm no erro — ofereça-as
   e repita o POST com o horário escolhido.

## Convenções (valem em toda rota)

- **Erros**: sempre `{code, message, hint, retryable}` — o `hint` é escrito
  para o agente agir; quando possível a saída já vem no payload.
- **Tempo**: entrada e saída em ISO 8601 **com offset** (America/Sao_Paulo na
  borda); datetime sem fuso é recusado (`DATA_SEM_FUSO`). Toda saída de
  horário traz `label_humano` pronto para falar com o cliente.
- **Idempotência**: escritas aceitam o header `Idempotency-Key` — repetir a
  chamada com a mesma chave devolve a resposta original, sem duplicar efeito.
- **Ações irreversíveis** (cancelar) disparadas por agente exigem confirmação
  humana: a primeira chamada devolve 409 `CONFIRMACAO_NECESSARIA` com prévia e
  `confirmation_token`; repita com o token após o OK (expira em 5 min).
- **Dinheiro** trafega como string decimal (`"80.00"`); **listagens** paginam
  por `limit`/`cursor`.

## Autenticação e escopos

`Authorization: Bearer <jwt do Supabase>` (humanos/UI) ou `X-Agent-Key`
(agentes — fase 1 do conector). Escopos: `agenda:read` (consultar),
`agenda:write` (criar/alterar), `agenda:cancel` (cancelar). Cada rota declara
o escopo que exige.
"""

TAGS = [
    {"name": "saúde", "description": "Liveness/readiness — sem autenticação."},
    {
        "name": "catálogo",
        "description": "Serviços e recursos (RF-01). Comece por aqui: o `service_id` é a chave de todo o resto.",
    },
    {
        "name": "grade",
        "description": "Janelas semanais de trabalho e bloqueios pontuais (RF-02). É o que o motor de slots oferece.",
    },
    {
        "name": "slots",
        "description": "Disponibilidade real (RF-02): grade − bloqueios − agendamentos − buffers. Consulte SEMPRE antes de agendar.",
    },
    {
        "name": "agendamentos",
        "description": "Agendar, reagendar, cancelar, confirmar (RF-03..06). Double-booking é impossível por constraint no banco.",
    },
    {
        "name": "recorrência",
        "description": "Séries semanais/quinzenais (RF-15). Cada ocorrência é um compromisso próprio ligado ao `series_id`.",
    },
]

app = FastAPI(
    title="Agenda Inteligente — agenda-service",
    version="0.2.0",
    description=DESCRICAO,
    openapi_tags=TAGS,
    servers=[{"url": "https://cpdf-agenda.better-knowledge.com", "description": "Protótipo do programa"}],
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
app.include_router(recorrencia.router)


def openapi_contrato():
    """Gera o schema e estampa o que o FastAPI não cobre sozinho:
    security schemes, escopo por operação e auth opcional no /health."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=TAGS,
        servers=app.servers,
    )
    schema.setdefault("components", {})["securitySchemes"] = {
        "SupabaseJWT": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT do Supabase Auth com claim `org_id` — humanos e UI.",
        },
        "AgentKey": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Agent-Key",
            "description": (
                "Chave estática de agente (fase 1 do conector — vira OAuth 2.1 no "
                "agenda-mcp). Ações irreversíveis pedem confirmação humana."
            ),
        },
    }
    schema["security"] = [{"SupabaseJWT": []}, {"AgentKey": []}]
    for caminho, operacoes in schema["paths"].items():
        for op in operacoes.values():
            if caminho.startswith("/health"):
                op["security"] = []  # liveness não exige credencial
                continue
            if escopo := op.get("x-escopo-requerido"):
                op["description"] = (
                    f"**Escopo:** `{escopo}`\n\n{op.get('description', '')}".strip()
                )
    app.openapi_schema = schema
    return schema


app.openapi = openapi_contrato


@app.get("/docs", include_in_schema=False)
async def scalar_docs():
    return get_scalar_api_reference(openapi_url=app.openapi_url, title=app.title)
