# cpdf-agenda
### Agenda Inteligente — sua agenda operada inteiramente por conversa

**Módulo 02 de 04** do programa **AS/IA Avançado — Dos Agentes aos Sistemas
Inteligentes** (CPDF). Marcar, remarcar, confirmar e cancelar pelo WhatsApp,
com lembretes que disparam com o notebook desligado.

**Status:** base do projeto pronta (etapas 1–4 parciais do plano §17) —
schema com RLS e constraint anti-double-booking, motor de slots, agendamento/
reagendamento/cancelamento, canal com drivers Evolution+Z-API, template-first
e opt-out. Faltam: espelho de tarefas, Google Calendar, .ics, link público,
fila de espera, recorrência, Calendly, `agenda-mcp` e as telas.

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
docs/             PRD e contrato de arquitetura
docker-compose.yml + Caddyfile   deploy no VPS (TLS automático)
```

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
