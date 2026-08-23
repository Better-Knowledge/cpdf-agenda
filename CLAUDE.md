# CLAUDE.md — cpdf-agenda

## O que é este repo
Agenda Inteligente (`agenda-service`) + canal de mensageria (`canal-service`) —
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
- Trocar driver do canal (telegram↔evolution↔zapi) é configuração — a mesma suíte
  passa nos três, inclusive num canal que não usa telefone.
- **Endereço do cliente** é por canal: E.164 no WhatsApp, `tg:<chat_id>` no Telegram.
  O campo `telefone` significa "endereço neste canal" — nunca assuma número.
  Sempre compare endereços por `enderecos.normalizar()`, nunca as strings cruas:
  desde o RF-19 essa comparação decide acesso.
- **Autoridade vem da credencial, não da autenticação** (RF-18): autenticar não
  concede tudo. Agente de atendimento (canal) e agente administrativo (MCP) têm
  escopos diferentes, e `exigir_escopo` de fato barra. O escopo declarado no
  OpenAPI é o mesmo cobrado em execução — não deixe divergir.
  Toda credencial vive em `agent_credentials`: **chave estática em variável de
  ambiente não autentica** (`AGENT_API_KEYS` foi removida). `X-Agent-Key` é só
  outro jeito de mandar o mesmo `agk_…`.
- **`credenciais:admin` nunca entra em preset de credencial de agente** e
  **não é delegável por rota** (`POST /credenciais` recusa com
  `ESCOPO_NAO_DELEGAVEL`): um token que emite tokens sobrevive à própria
  revogação. A primeira credencial da org nasce em `make credencial`; a gestão
  do dia a dia é por rota e pela tela T-11.
- **Auditoria mora no agenda-service, não no conector MCP** (`00` §5.8): no
  conector, as ações do agente de atendimento — que não passa por MCP — não
  seriam vistas. Entram escritas e recusas por autoridade; leitura bem-sucedida
  não entra. `args_hash` cobre rota + `Idempotency-Key`, nunca o corpo.
- **Conector MCP não tem credencial própria** (§14.5): o `agenda-admin-mcp`
  repassa o bearer de quem chamou e **nunca decide autorização** — quem recusa
  é a agenda, com o mesmo 403 que daria a um `curl`. Uma chave de serviço no
  `.env` dele recria o confused deputy que o RF-18 eliminou (teste:
  `test_o_conector_nao_tem_credencial_propria`).
- **O titular é cunhado onde o endereço é provado** (RF-19): dentro do
  `canal-service`, depois do `compare_digest` do token de webhook, e viaja
  assinado (`ats_…`, HMAC, 30 min). Nenhum serviço declara por quem age —
  header auto-declarado é o ator restringido definindo a própria restrição.
  Compromisso de outro titular responde **404**, nunca 403.

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
