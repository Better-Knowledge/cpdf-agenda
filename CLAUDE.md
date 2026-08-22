# CLAUDE.md — cpdf-agenda

## O que é este repo
Agenda Inteligente (`agenda-service`) + canal de WhatsApp (`canal-service`) —
módulo 02 do AS/IA Avançado. Agendamento por conversa, lembretes automáticos,
conector MCP. O canal nasce aqui e é consumido pelos módulos 03 e 04.

## Leia antes de codar
1. `docs/PRD.md` — requisitos com critérios de aceite (RF-01..11, §8 IA, §13 MCP)
2. `docs/00-ARQUITETURA-BASE.md` — contrato comum: §4.8 (canal), §5 (MCP/agent-friendly)
3. Schemas de eventos: https://github.com/Better-Knowledge/cpdf-comum

## Stack (não mude sem atualizar o PRD)
- Python 3.12+ · FastAPI · Pydantic v2 · SQLAlchemy 2.0 · Alembic
- Supabase (Postgres 15+) — RLS em toda tabela de negócio
- Front: Vite + React (SPA) — sem Next.js neste repo
- MCP: SDK Python oficial, Streamable HTTP (o transporte HTTP+SSE antigo está depreciado)
- Deploy: VPS com Docker Compose + Caddy; jobs com APScheduler

## Invariantes (protegidas por teste — não relaxe)
- **Zero double-booking**: `EXCLUDE USING gist (resource_id WITH =, periodo WITH &&)`
  no banco. A regra vive no Postgres, nunca só na aplicação.
- **Tempo**: `tstzrange`/UTC no banco; America/Sao_Paulo na borda; datetime naive é proibido.
  Toda saída de horário: ISO 8601 com offset + `label_humano`.
- **Template-first**: mensagem ativa (lembrete/confirmação/cobrança) é SEMPRE template
  do canal — `POST /canal/enviar` recusa `tipo=sessao` para mensagem ativa.
- **Opt-out determinístico**: "SAIR" é detectado por regra ANTES de qualquer LLM;
  envio ativo consulta `channel_optouts` sempre.
- **Reagendamento atômico**: novo slot reservado e antigo liberado na mesma
  transação, ou nada muda.
- Trocar driver do canal (evolution↔zapi) é configuração — a mesma suíte passa nos dois.

## Convenções do programa
- Toda tabela: `org_id uuid not null` + RLS `org_id = auth.jwt() ->> 'org_id'`
- Toda escrita aceita `Idempotency-Key`; repetição não duplica efeito
- Erros: `{code, message, hint, retryable}` — o `hint` é escrito para o agente ler
  (ex.: já traz as 3 alternativas de horário no payload)
- Toda listagem paginada (`limit`/`cursor`); dinheiro `numeric(14,2)`, string na API
- Migrations reversíveis (`alembic downgrade` testado)
- Cancelamento exige confirmação humana (elicitation MCP ou `confirmation_token`)

## Não faça
- Não chame API de WhatsApp direto de nenhum módulo — sempre via `canal-service`
- Não configure o número pessoal do aluno no canal (o produto recusa)
- Não interprete data ambígua: pergunte; repita a data por extenso antes de confirmar
- Não coloque segredo em log, git ou resposta de API — `.env` no VPS, cifrado no banco
