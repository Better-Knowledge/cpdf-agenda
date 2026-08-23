# cpdf-agenda
### Agenda Inteligente — sua agenda operada inteiramente por conversa

**Módulo 02 de 04** do programa **AS/IA Avançado — Dos Agentes aos Sistemas
Inteligentes** (CPDF). Marcar, remarcar, confirmar e cancelar pelo WhatsApp,
com lembretes que disparam com o notebook desligado.

**Status:** etapas 1–6 do plano §17 — schema com RLS e constraint
anti-double-booking, motor de slots, agendamento/reagendamento/cancelamento,
recorrência, contrato OpenAPI com exemplos, UI do prestador, canal ligado a
uma instância real de WhatsApp (QR pela própria UI) e o agente respondendo o
inbound. Faltam: espelho de tarefas, fila de espera, Google Calendar, .ics,
link público, Calendly e o `agenda-mcp`.

## O que este módulo entrega
- Serviços, grade de disponibilidade e motor de slots sem double-booking
  (garantido no banco, `EXCLUDE USING gist`)
- **`canal-service`** — adapter WhatsApp com drivers Evolution + Z-API
  (Meta como interface/aula), templates, inbound e opt-out. Nasce aqui e é
  reutilizado pelos módulos 03 e 04
- Confirmações e lembretes automáticos via template
- Espelho no [Gestor de Tarefas](https://github.com/Better-Knowledge/cpdf-gestor-tarefas)
  e feed .ics para Google/Apple Calendar
- Conector MCP `agenda-mcp` (OAuth 2.1) para operação por agentes remotos

## Stack (canônica do programa)
Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 + Alembic · Supabase
(Postgres + RLS) · Vite + React · VPS (Docker Compose + Caddy) · MCP Python SDK

## Comece por aqui
1. [docs/PRD.md](docs/PRD.md) — o que construir, com critérios de aceite
2. [docs/00-ARQUITETURA-BASE.md](docs/00-ARQUITETURA-BASE.md) — contrato comum
   (cópia congelada; fonte: [cpdf-comum](https://github.com/Better-Knowledge/cpdf-comum))
3. [CLAUDE.md](CLAUDE.md) — instruções para agentes de código

## Estrutura do repositório

```
agenda-service/   FastAPI + SQLAlchemy + Alembic — API da agenda (OpenAPI no /docs via Scalar)
canal-service/    adapter WhatsApp (evolution|zapi implementados; meta = interface/aula)
agente-service/   orquestrador do inbound (IA-04) — classifica a intenção e age pela API
web/              UI do prestador (Vite + React, servida em /app) — segundo cliente da API
docs/             PRD, contrato de arquitetura e openapi.json (artefato versionado)
docker-compose.yml + Caddyfile   deploy no VPS (TLS automático)
```

As telas seguem o princípio do PRD §12: nenhuma chama banco ou tem regra
própria — toda ação passa pela API pública. Telas entregues: T-01 (chave de
acesso, fase 1), T-02 (agenda do dia), T-03 (detalhe + ações), T-04
(serviços), T-05 (grade e bloqueios), T-09 (canal: driver, QR code, templates
e opt-outs). `make web-dev` roda a UI local com proxy para a API.

### Como o inbound funciona

O WhatsApp do cliente chega no `canal-service`, que verifica o segredo,
registra a mensagem e trata **opt-out por regra** (nunca por IA). Só então a
mensagem normalizada segue ao `agente-service`, que classifica a intenção
(IA-04) e age pela API da agenda — nunca pelo banco. O gradiente de risco do
programa vale literalmente: confirmar presença é automático, remarcar é
**proposto** (o agente oferece horários e o cliente escolhe) e cancelar
**nunca** é automático — vai para o humano, porque libera o slot para outra
pessoa. Intenção incerta vira pergunta; incerta duas vezes vira
"aguardando humano".

Sem `ANTHROPIC_API_KEY` o agente roda **só com as regras determinísticas** — o
que elas não reconhecem vai para o humano. Sem `ORQUESTRADOR_URL`, o canal
apenas registra o inbound e ninguém responde automaticamente.

## Desenvolvimento

Pré-requisitos: Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker.

```bash
cp .env.example .env          # ajuste os segredos
make dev-db                   # Postgres local (produção usa Supabase)
make migrate migrate-canal    # aplica os schemas (Alembic)
make test                     # suíte completa (invariantes protegidas por teste)

cd agenda-service && uv run uvicorn app.main:app --reload   # http://localhost:8000/docs
```

Os testes de integração criam sozinhos os bancos `agenda_test`/`canal_test`
com um role **não-superuser** (superuser ignora RLS — testar com ele seria
teatro). Sem Postgres disponível, os testes de integração são pulados e os de
unidade rodam normalmente.

## Ecossistema
| Módulo | Repo |
|---|---|
| 01 · CRM | [cpdf-crm-mentoria](https://github.com/Better-Knowledge/cpdf-crm-mentoria) |
| **02 · Agenda** | **este repo** |
| 03 · Pedidos | [cpdf-pedidos](https://github.com/Better-Knowledge/cpdf-pedidos) |
| 04 · Financeiro | [cpdf-financeiro](https://github.com/Better-Knowledge/cpdf-financeiro) |
| Contrato comum | [cpdf-comum](https://github.com/Better-Knowledge/cpdf-comum) |
