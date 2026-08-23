# cpdf-agenda
### Agenda Inteligente — sua agenda operada inteiramente por conversa

**Módulo 02 de 04** do programa **AS/IA Avançado — Dos Agentes aos Sistemas
Inteligentes** (CPDF). Marcar, remarcar, confirmar e cancelar pelo WhatsApp,
com lembretes que disparam com o notebook desligado.

**Status:** etapas 1–7 do plano §17, mais a separação de papéis (etapa 9 em
curso) — schema com RLS e constraint anti-double-booking, motor de slots,
agendamento/reagendamento/cancelamento, recorrência, contrato OpenAPI com
exemplos, UI do prestador, canal ligado a WhatsApp e Telegram reais, agente
respondendo o inbound, fila de espera, risco de no-show, **autoridade por
credencial** (RF-18), **isolamento por titular** (RF-19), superfície
administrativa completa (catálogo, grade declarativa, credenciais) e
auditoria. Faltam: espelho de tarefas, Google Calendar, .ics, link público,
Calendly e os conectores MCP.

## O que este módulo entrega
- Serviços, grade de disponibilidade e motor de slots sem double-booking
  (garantido no banco, `EXCLUDE USING gist`)
- **`canal-service`** — adapter de mensageria com drivers Telegram, Evolution e
  Z-API (Meta como interface/aula), templates, inbound e opt-out. Nasce aqui e
  é reutilizado pelos módulos 03 e 04
- Confirmações e lembretes automáticos via template
- Espelho no [Gestor de Tarefas](https://github.com/Better-Knowledge/cpdf-gestor-tarefas)
  e feed .ics para Google/Apple Calendar
- **Dois papéis de agente com autoridades verificadas** (RF-18): quem atende o
  cliente final alcança o compromisso daquele cliente; quem opera a plataforma
  usa credencial administrativa. Credenciais em tabela, revogáveis, com escopo
  ajustável uma a uma
- Conectores MCP: `agenda-mcp` (atendimento) e **`agenda-admin-mcp`** — a
  equipe criando agendas, grade e consultando apontamentos por conversa

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
canal-service/    adapter de mensageria (telegram|evolution|zapi; meta = interface/aula)
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

### Testar em um minuto: Telegram

O caminho mais curto para ver o produto funcionando — sem chip, sem QR code,
sem risco de bloqueio:

1. No Telegram, fale com o **@BotFather** e mande `/newbot`. Guarde o token.
2. Na UI, aba **Canal** → driver **Telegram** → cole o token → salvar.
3. Clique em **Ativar o bot** (o canal registra o webhook sozinho).
4. Procure o seu bot no Telegram, mande `/start` e escreva.

Requisito de infra: o Telegram é serviço de nuvem e só entrega inbound por
HTTPS público, então `WEBHOOK_BASE_URL_PUBLICA` precisa apontar para um domínio
que exponha **apenas** `/webhooks/canal/` (o resto do canal continua fechado —
ver `docker-compose.override.yml`). Já o Evolution, que roda no mesmo Docker,
segue conversando pela rede interna.

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
