# cpdf-agenda
### Agenda Inteligente — sua agenda operada inteiramente por conversa

**Módulo 02 de 04** do programa **AS/IA Avançado — Dos Agentes aos Sistemas
Inteligentes** (CPDF). Marcar, remarcar, confirmar e cancelar pelo WhatsApp,
com lembretes que disparam com o notebook desligado.

**Status:** as dez etapas do plano §17 entregues — schema com RLS e constraint
anti-double-booking, motor de slots, agendamento/reagendamento/cancelamento,
recorrência, contrato OpenAPI com exemplos, UI do prestador, canal ligado a
WhatsApp e Telegram reais, agente respondendo o inbound, fila de espera, risco
de no-show, **autoridade por credencial** (RF-18), **isolamento por titular**
(RF-19), auditoria, **Google Calendar** (push + busy-read), **feed .ics**,
**link público**, **importação do Calendly**, métricas, e os **dois conectores
MCP** (atendimento e administração). Fora do escopo do módulo: o espelho de
tarefas (RF-07), que depende do módulo 03.

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
- **Google Calendar** (RF-12): o compromisso aparece no calendário do
  prestador em menos de um minuto, e reunião marcada direto lá bloqueia o
  horário aqui. Falha do Google nunca impede agendar
- **Link público** de auto-agendamento (RF-13) e **feed .ics** (RF-11), para
  quem prefere clicar e para quem não quer conectar OAuth
- **Dois conectores MCP** — `agenda-mcp` (atendimento: 8 tools, alcança um
  cliente por vez) e `agenda-admin-mcp` (a equipe: 11 tools de operação).
  Nenhum dos dois tem chave própria: repassam a de quem chamou e nunca decidem
  autorização

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
agenda-mcp/       conector MCP de atendimento (Streamable HTTP) — 8 tools, um cliente por vez
agenda-admin-mcp/ conector MCP administrativo (Streamable HTTP) — 11 tools, sem credencial própria
web/              UI do prestador (Vite + React, servida em /app) — segundo cliente da API
docs/             PRD, contrato de arquitetura e openapi.json (artefato versionado)
docker-compose.yml + Caddyfile   deploy no VPS (TLS automático)
```

As telas seguem o princípio do PRD §12: nenhuma chama banco ou tem regra
própria — toda ação passa pela API pública. Telas entregues: T-01 (chave de
acesso, fase 1), T-02 (agenda do dia), T-03 (detalhe + ações), T-04
(serviços), T-05 (grade e bloqueios), T-06 (fila de espera), T-09 (canal:
driver, QR code, templates e opt-outs), T-07 (links públicos), T-08
(calendários: Google, .ics e Calendly), T-10 (os números do §4) e T-11 (chaves
de acesso: emitir, revogar e ver o último uso). A página pública P-01
(`/app/agendar/<slug>`) é a única sem credencial — e não importa nada do
painel. `make web-dev` roda a UI local com proxy para a API.


### Os dois conectores MCP

São **dois servidores porque são duas autoridades** (PRD §14). Com um só, a
separação dependeria de cada tool lembrar de conferir escopo — e a tool nova,
escrita com pressa, esqueceria. Com dois, as ferramentas administrativas
simplesmente **não existem** no endpoint que o lado de atendimento alcança: a
fronteira vira topologia, não disciplina.

`agenda-mcp` (`https://mcp.SEU-DOMINIO.com/agenda/mcp`) publica as 8 tools de
atendimento. A credencial dele é, tipicamente, o token de sessão `ats_…` que o
`canal-service` cunhou depois de provar o endereço de quem escreveu — por isso
"meus compromissos" quer dizer os daquela pessoa. Ele entende data em
português ("quinta de tarde", "semana que vem") e, quando a expressão é
ambígua, devolve a **pergunta** a fazer ao cliente em vez de adivinhar.

`make mcp-atendimento` sobe esse conector em `http://127.0.0.1:8101/mcp`.

`agenda-admin-mcp` publica 11 tools em Streamable HTTP
(`https://mcp.SEU-DOMINIO.com/agenda/admin/mcp`). A credencial é o
`Authorization: Bearer agk_…` da própria conexão — emitido na tela de
Integrações ou por `make credencial`. O conector **repassa** esse token e não
decide nada: quem recusa é a agenda, com o mesmo 403 que daria a um `curl`.

As operações são declarativas de propósito. `agenda_admin_grade_definir`
recebe a semana inteira e o servidor faz a diferença numa transação — listar,
remover uma, criar duas e não esquecer nenhuma é exatamente a sequência em que
um modelo erra. Cancelar passa por confirmação humana (elicitation, com
`confirmation_token` como fallback) e nunca é decisão do agente.

`make mcp-dev` sobe o conector em `http://127.0.0.1:8100/mcp` para inspecionar
com o MCP Inspector.

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

A primeira credencial de uma organização nasce no servidor — uma rota capaz de
emitir credencial administrativa seria um backdoor permanente:

```bash
make credencial ORG=<uuid> NOME="Painel do prestador" PAPEL=administrativo
```

Daí em diante a gestão é pela tela de Integrações (T-11). Os alvos `make`
assumem `DATABASE_URL` no ambiente; no VPS o mesmo comando roda dentro do
contêiner (`docker compose exec agenda-service uv run python -m app.admin_cli …`).

## Atualizando um protótipo já no ar

Esta versão fecha os dois caminhos de autenticação legados, e a ordem importa —
fora dela, o bot do WhatsApp para de responder.

1. **Migre as chaves antigas** (antes de tirá-las do `.env`). O valor é
   preservado, então ninguém é deslogado do painel:

   ```bash
   docker compose exec agenda-service uv run python -m app.admin_cli importar-env
   ```

2. **Gere o segredo da sessão de atendimento** e ponha no `.env`. Ele é
   compartilhado: o canal cunha o token, a agenda o valida, e valores
   diferentes fazem toda conversa virar 401.

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"   # SESSAO_ATENDIMENTO_SECRET
   ```

3. **Informe o domínio do conector MCP** (`MCP_HOSTS_PERMITIDOS`) — sem ele o
   `agenda-admin-mcp` não sobe, de propósito: com a proteção de DNS rebinding
   ligada e a lista vazia, ele responderia 421 a tudo, o que pareceria falha
   de rede.

4. **Suba tudo junto** (`make up`). Agenda, canal e agente precisam virar na
   mesma janela: é o canal que passa a cunhar o token e o agente que passa a
   apresentá-lo.

5. **Remova `AGENT_API_KEYS` do `.env`.** A autenticação não a lê mais.

Deu errado no meio? `ATENDIMENTO_ISOLADO=0` devolve o comportamento antigo do
`X-Service-Key` sem redeploy do código. É alavanca de emergência, não
configuração: com ela desligada, um único segredo de ambiente volta a valer
por todos os clientes da organização.

### A demo final

`docs/ROTEIRO-DEMO.md` traz o roteiro de 20 minutos: a equipe monta a agenda
por conversa, um cliente marca pelo WhatsApp, o isolamento é demonstrado com
`curl`, o cancelamento oferta o horário à fila, o compromisso aparece no
Google Calendar — e o notebook do apresentador pode ser fechado, porque os
lembretes rodam no VPS.

## Licença e atribuição

**Apache License 2.0** — texto completo em [LICENSE](LICENSE), atribuição em
[NOTICE](NOTICE).

Autoria: **Fernando Melo Faraco** (<fernando.faraco@better-knowledge.com.br>),
**Comunidade Profissionais do Futuro (CPDF)** e **Better-Knowledge**.

A atribuição é **obrigatória**, e o mecanismo é o arquivo `NOTICE`: a Seção
4(d) da licença faz da preservação dele uma condição, não uma cortesia. Quem
redistribuir este software — com ou sem modificações, em código ou compilado —
precisa entregar uma cópia legível daquele aviso, seja no `NOTICE` da obra
derivada, na documentação que acompanha a distribuição, ou numa tela do
produto onde avisos de terceiros costumam aparecer. Arquivos modificados
precisam dizer que foram modificados (4(b)), e os avisos de copyright e
atribuição no código-fonte precisam ser preservados (4(c)).

O que a Apache 2.0 **não** faz é obrigar quem usa o software a exibir o seu
nome — obrigação de propaganda é justamente o que a licença evita. Se o
requisito for "todo aplicativo derivado mostra o crédito na interface", isso
não cabe na Apache 2.0: seria uma licença diferente, e chamá-la de Apache
2.0 confundiria quem lê.

## Ecossistema
| Módulo | Repo |
|---|---|
| 01 · CRM | [cpdf-crm-mentoria](https://github.com/Better-Knowledge/cpdf-crm-mentoria) |
| **02 · Agenda** | **este repo** |
| 03 · Pedidos | [cpdf-pedidos](https://github.com/Better-Knowledge/cpdf-pedidos) |
| 04 · Financeiro | [cpdf-financeiro](https://github.com/Better-Knowledge/cpdf-financeiro) |
| Contrato comum | [cpdf-comum](https://github.com/Better-Knowledge/cpdf-comum) |
