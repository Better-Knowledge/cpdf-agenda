# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

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

from .auditoria import Auditoria
from .config import settings
from .errors import instalar_handlers
from .jobs import criar_scheduler
from .routers import (
    appointments,
    availability,
    booking_links,
    calendly,
    canal,
    credenciais,
    health,
    ics,
    integracoes,
    metricas,
    recorrencia,
    resources,
    services,
    slots,
    waitlist,
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

`Authorization: Bearer <token>` — `agk_…` (credencial de agente, revogável),
`ats_…` (sessão de atendimento, cunhada pelo canal) ou JWT do Supabase
(humanos/UI). `X-Agent-Key` carrega o mesmo `agk_…` num header próprio, que é
como a UI fala hoje; sai quando o Supabase Auth entrar. Toda credencial vive
em `agent_credentials`: chave estática em variável de ambiente não autentica.

**Autenticar não concede tudo.** Cada rota declara o escopo que exige, e é o
mesmo cobrado em execução:

| Escopo | Cobre |
|---|---|
| `agenda:read` | catálogo, horários livres, grade, o **próprio** compromisso |
| `agenda:write` | agendar, remarcar, confirmar, fila — para **um** cliente |
| `agenda:cancel` | cancelar um compromisso |
| `agenda:operacao` | o dia inteiro, todos os compromissos, a fila completa, faltas |
| `agenda:admin` | serviços, recursos, grade e bloqueios |
| `canal:admin` | driver, credenciais do canal, templates, opt-outs |
| `credenciais:admin` | emitir e revogar credenciais — nunca num preset de agente |

Uma credencial de **atendimento** (o bot do canal) carrega ainda um
`titular`: ela alcança só o compromisso do cliente daquela conversa, e
compromisso de terceiro responde 404. Consulte `GET /credenciais/eu` para
descobrir a própria autoridade antes de tentar uma ação.
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
    {
        "name": "fila de espera",
        "description": (
            "Fila por janela de horário (RF-14). Cancelamento que libera horário "
            "compatível oferta ao primeiro da fila pelo canal — **sem reserva**: o "
            "horário segue livre e quem confirmar primeiro leva."
        ),
    },
    {
        "name": "credenciais",
        "description": (
            "Papéis e escopos. Um agente de **atendimento** (canal) alcança só o "
            "compromisso do cliente que atende; um agente **administrativo** (via MCP) "
            "configura a plataforma. Emitir credencial é operação de CLI, nunca de rota."
        ),
    },
    {
        "name": "calendário",
        "description": (
            "Feed .ics somente-leitura (RF-11) — a opção de calendário sem OAuth. "
            "O segredo é o token na URL: revogável, e com modo `privado` que mostra "
            "só 'Ocupado'. É **visão consolidada, não notificação**."
        ),
    },
    {
        "name": "integrações",
        "description": (
            "Google Calendar (RF-12): push de evento em < 60 s e busy-read no motor "
            "de slots. Falha do Google nunca bloqueia agendamento — o push tem fila "
            "com retry e o busy-read degrada para o cálculo local."
        ),
    },
    {
        "name": "link público",
        "description": (
            "Auto-agendamento por link (RF-13) — a via opcional, para o cliente que "
            "prefere clicar. A página pública usa o **mesmo** motor de slots e o "
            "mesmo caminho de criação: sem rota privilegiada, com limite por IP e "
            "coleta mínima."
        ),
    },
    {
        "name": "calendly",
        "description": (
            "Importação one-way do Calendly (RF-16), **opcional**: sem configurar, "
            "nada muda. O que é marcado lá aparece aqui e ocupa o horário; a agenda "
            "nunca escreve no Calendly."
        ),
    },
    {
        "name": "métricas",
        "description": (
            "Os números do §4 no período: ocupação, faltas, confirmações e origem dos "
            "agendamentos. Percentual sem base de cálculo volta `null`, nunca `0`."
        ),
    },
    {
        "name": "canal",
        "description": (
            "Canal de mensagens (T-09), por procuração: a UI fala com o agenda-service e "
            "ele repassa ao canal-service — que nunca é exposto ao navegador. Drivers: "
            "`telegram` (bot, o mais simples de testar), `evolution` e `zapi` (WhatsApp), "
            "`meta` (extensão). Credenciais são write-only."
        ),
    },
]

app = FastAPI(
    title="Agenda Inteligente — agenda-service",
    version="0.4.0",
    description=DESCRICAO,
    openapi_tags=TAGS,
    servers=[{"url": "https://cpdf-agenda.better-knowledge.com", "description": "Protótipo do programa"}],
    docs_url=None,  # /docs é o Scalar (RF-17)
    redoc_url=None,
    lifespan=lifespan,
)

# Mais externo de propósito: precisa ver o status final da resposta, inclusive
# o que os exception handlers produzem.
app.add_middleware(Auditoria)

instalar_handlers(app)
app.include_router(health.router)
app.include_router(services.router)
app.include_router(resources.router)
app.include_router(availability.router)
app.include_router(slots.router)
app.include_router(appointments.router)
app.include_router(recorrencia.router)
app.include_router(waitlist.router)
app.include_router(canal.router)
app.include_router(credenciais.router)
app.include_router(ics.router)
app.include_router(integracoes.router)
app.include_router(booking_links.router)
app.include_router(calendly.router)
app.include_router(metricas.router)


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
                "O mesmo token `agk_…` do bearer, num header próprio — é como a UI "
                "fala hoje, e resolve em `agent_credentials` do mesmo jeito. Prefira "
                "`Authorization: Bearer agk_…` em integrações novas. Ações "
                "irreversíveis pedem confirmação humana."
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
