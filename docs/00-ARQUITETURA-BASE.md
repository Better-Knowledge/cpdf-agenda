> **Cópia congelada** (v1 · 2026-08-22) do contrato comum. Fonte da verdade: [Better-Knowledge/cpdf-comum](https://github.com/Better-Knowledge/cpdf-comum) — mudanças de contrato acontecem lá primeiro.

# AS/IA Avançado — Documento Base de Arquitetura
### Contrato comum aos 4 PRDs (leia antes dos módulos)

> **Status:** Baseline v1 · **Escopo:** compartilhado pelos 4 aplicativos
> **Origem:** Ementa "Dos Agentes aos Sistemas Inteligentes — Turma Avançada"

---

## 1. A tese do programa

A turma básica provou que o agente funciona. O problema agora não é capacidade
do agente — é **topologia**: o sistema mora na máquina do aluno.

| Dor de hoje | Estado alvo |
|---|---|
| SQLite local, um arquivo só seu | Supabase na nuvem, com RLS e backup |
| API viva só enquanto o notebook está ligado | FastAPI em VPS, 24/7 |
| Cada sistema é uma ilha | 4 domínios, 1 barramento, 1 agente |
| O agente responde mas não executa até o fim | O agente fecha o ciclo e escreve no banco |

**Promessa final do programa (aceite do conjunto):** uma oportunidade marcada como
*ganha* no CRM gera contrato, lança receitas, reserva estoque, agenda a entrega e
cria a primeira tarefa de cobrança — **sem abrir um sistema sequer**.

---

## 2. Os quatro aplicativos

| # | App | Serviço | Entrega o quê | Demo de aceite |
|---|---|---|---|---|
| 01 | CRM Revisitado | `crm-service` | Funil, propostas, reuniões→IA, migração+deploy | Reunião vira resumo, registro e follow-up |
| 02 | Agenda Inteligente | `agenda-service` | Serviços, grade, lembretes, espelho em tarefas | Marcar, reagendar e confirmar por conversa |
| 03 | Catálogo e Pedidos | `pedidos-service` | Catálogo, estoque, baixa, reposição | Item em falta → substituto → venda → reposição |
| 04 | Financeiro e Contratos | `financeiro-service` | Contratos, AR/AP, caixa 30/60/90, cobrança | Venda ganha → contrato + receitas + cobrança |

Os módulos são **sequenciais**: cada um depende apenas do anterior, e ao final de
cada módulo o sistema fica funcionando.

---

## 3. Stack

### 3.1 O que é igual nos quatro módulos (não negociável)

| Camada | Escolha | Observação |
|---|---|---|
| Banco | **Supabase** (Postgres 15+) | RLS ligado em todas as tabelas de negócio |
| Auth | **Supabase Auth** | fonte do `org_id` que a RLS usa |
| **Camada de agente** | **1 MCP server por app** (Streamable HTTP + OAuth 2.1) | fachada fina sobre a API — §5 |
| Agente | 1 orquestrador (LLM + clientes MCP) | consome as APIs via MCP, nunca o banco direto |
| Tarefas | `tasks-service` (**pré-existente**, turma básica) | destino de todo "próximo passo" |
| Canal de mensagens | `canal-service` — adapter WhatsApp com 3 drivers | mensagem ativa é template — §4.8 |
| Contrato entre módulos | `domain_events` (§4.4) | mesmo formato nos quatro |
| Observabilidade | log estruturado JSON + `/health` + Sentry (opcional) | |

**As fronteiras são idênticas nos quatro módulos.** É isso que permite misturar
stacks sem virar bagunça: banco, segurança, conector MCP e contrato de eventos
não mudam. Só o miolo muda.

### 3.2 Stack canônica e excursão de contraste

O programa tem **uma stack recomendada** — a **canônica** — e **uma excursão
deliberada** fora dela. Não são duas opções de mesmo peso: o programa forma o
aluno na canônica (módulos 01, 02 e 04); o módulo 03 é o contraste, que ensina a
reconhecer e avaliar a alternativa que os agentes entregam por padrão. A
justificativa completa, escrita para aluno não-desenvolvedor, está em
[`05-STACKS-E-ESCOLHAS.md`](05-STACKS-E-ESCOLHAS.md).

**Por que esta é a canônica** (resumo executivo; detalhe no doc 05):
1. **Agentes erram menos, e o aluno percebe mais rápido** — idioma estável há
   anos, o mais representado no treino dos modelos, erros que apontam a linha.
2. **Segurança estrutural** — RLS no banco + fronteira física cliente/servidor +
   OAuth com escopos no MCP. Nenhuma das três depende de revisão de código.
3. **Contrato de graça** — o OpenAPI é gerado do código e nunca desatualiza. Com
   4 repositórios escritos por agentes, contrato à mão é onde a drift começa.

| Módulo | Stack | Papel | Motivo que decide |
|---|---|---|---|
| **01 · CRM** | Canônica | formação | repo da turma básica é Python; migração e IA de reunião |
| **02 · Agenda** | Canônica | formação | fuso/horário de verão e lembretes frequentes exigem servidor livre |
| **03 · Catálogo e Pedidos** | **Excursão (Next.js)** | contraste | é o que o agente entrega por padrão; a lição de hospedagem se aprende publicando |
| **04 · Financeiro** | Canônica | formação | precisão decimal em dinheiro — não é preferência |

**A stack canônica — FastAPI + Supabase + Vite/React, publicada em VPS** (módulos 01 · 02 · 04)

| Camada | Escolha |
|---|---|
| API | FastAPI (Python 3.11+) + Pydantic v2 — OpenAPI é o contrato do agente |
| ORM/acesso | SQLAlchemy 2.0 + Alembic (migrations versionadas em git) |
| Front | **Vite + React** (SPA), consumindo a API — sem Next.js: não há servidor JS aqui |
| Jobs | APScheduler ou worker + `cron` no VPS |
| Deploy | **VPS** Linux + Docker Compose + Caddy (TLS) |

**A excursão — Next.js full-stack** (módulo 03, apenas)

| Camada | Escolha |
|---|---|
| App | Next.js (App Router) — UI e servidor no mesmo projeto |
| Acesso a dados | cliente Supabase + Drizzle ou consultas tipadas |
| Contrato | OpenAPI **mantido explicitamente** (gerado de zod) — não sai de graça |
| Conector MCP | Route Handler no mesmo deploy (`/api/mcp`) |
| Jobs | agendamento **dentro do Supabase**, não na plataforma de hospedagem |
| Deploy | Vercel **ou** o mesmo VPS — ver §6 de `05-STACKS-E-ESCOLHAS.md` |

> ⚠️ **Duas armadilhas a citar em aula, não a descobrir em produção:** o plano
> gratuito da Vercel proíbe uso comercial, e rotina agendada é limitada nos
> planos baratos de plataformas serverless. As duas afetam a arquitetura antes de
> afetarem a conta.

**Premissa a validar na aula 1:** o Gestor de Tarefas da turma básica expõe (ou
receberá) uma API HTTP com `criar tarefa`, `atualizar status`, `listar por dono e
data`. Todos os 4 módulos escrevem nele.

---

## 4. Decisões transversais (valem para os 4 PRDs)

### 4.1 Multi-tenant e segurança
- Toda tabela de negócio carrega `org_id uuid not null`.
- **RLS obrigatória**: política padrão `org_id = auth.jwt() ->> 'org_id'`.
- A API usa `service_role` apenas no backend; o cliente nunca vê a chave.
- O agente autentica por **API key própria** (`X-Agent-Key`) mapeada para um
  `agent_user` com escopo por ferramenta — o agente não é superusuário.
- Segredos em `.env` no VPS (nunca no git); rotação documentada.

### 4.2 Contrato agente ↔ API
- Toda tool do agente é um endpoint REST documentado no OpenAPI.
- **Idempotência obrigatória** em toda escrita: header `Idempotency-Key`;
  repetição retorna o mesmo resultado, sem duplicar registro.
- **Confirmação humana** obrigatória antes de: cancelar compromisso, fechar
  pedido, emitir contrato e disparar cobrança. O agente propõe, o humano aprova.
- Erros retornam `{code, message, hint}` — `hint` é texto que o agente pode ler
  em voz alta para o usuário.

### 4.3 Dados e tempo
- Timezone canônico: **America/Sao_Paulo**; persistir em `timestamptz` UTC.
- Dinheiro: `numeric(14,2)`; nunca float. Moeda: BRL.
- Todo registro tem `created_at`, `updated_at`, `created_by`.
- Exclusão é **soft delete** (`deleted_at`) nas entidades de negócio.

### 4.4 Eventos entre módulos
Barramento simples: tabela `domain_events` no Supabase + polling do worker
(sem Kafka, sem fila externa — mantém o custo do aluno em pé).

```sql
create table domain_events (
  id           bigserial primary key,
  org_id       uuid not null,
  event_type   text not null,          -- ex: 'crm.opportunity.won'
  payload      jsonb not null,
  occurred_at  timestamptz not null default now(),
  processed_at timestamptz,
  attempts     int not null default 0,
  last_error   text
);
```

Eventos canônicos do programa:

| Evento | Emitido por | Consumido por |
|---|---|---|
| `crm.opportunity.won` | M1 | M4 (contrato+receitas), M3 (reserva), M2 (entrega) |
| `crm.meeting.summarized` | M1 | M1 (follow-up), tasks-service |
| `agenda.appointment.created/canceled` | M2 | tasks-service |
| `orders.order.confirmed` | M3 | M4 (receita), M1 (histórico do cliente) |
| `orders.stock.low` | M3 | tasks-service (reposição) |
| `finance.receivable.overdue` | M4 | tasks-service (cobrança) |

### 4.5 Migração SQLite → Supabase (padrão reaproveitado nos 4 módulos)
1. Inventário: tabelas, volumes, colunas, tipos, chaves.
2. Mapa de tipos SQLite→Postgres (`TEXT`→`text/uuid/timestamptz`, `REAL`→`numeric`).
3. Schema novo no Supabase via Alembic (nunca "dump direto").
4. Carga em staging (`_import_*`) → validação → `insert ... select`.
5. **Reconciliação**: contagem por tabela, somatório de valores, 10 amostras
   comparadas 1:1. Só então vira produção.
6. Congela o SQLite como `backup_YYYYMMDD.db` — não se apaga nada.

### 4.6 Definition of Done (todo módulo)
- [ ] Migrations aplicadas e reversíveis (`alembic downgrade` testado)
- [ ] RLS ativa e testada com dois `org_id` diferentes
- [ ] Endpoints no OpenAPI + exemplos de payload
- [ ] **Conector MCP publicado, autenticado e conectável de fora (§5)**
- [ ] Tools registradas no agente e testadas por conversa
- [ ] Deploy no VPS, HTTPS válido, `/health` verde
- [ ] Job agendado rodando com a máquina do aluno desligada
- [ ] **Demo final do módulo executada de ponta a ponta, ao vivo**
- [ ] README de operação (subir, derrubar, restaurar backup)

### 4.7 Fora de escopo do programa inteiro
App mobile nativo · multi-idioma · integração fiscal/NF-e · gateway de pagamento
com liquidação real · BI dedicado · marketplace de terceiros.

### 4.8 Canal de mensagens (WhatsApp) — decisão registrada

Um serviço transversal (`canal-service`, no mesmo VPS) concentra envio e
recebimento de mensagens para os módulos que falam com o cliente final. Nasce no
**módulo 2** (o primeiro que precisa dele) e é reutilizado por M3 (pedidos por
conversa) e M4 (cobrança). Nenhum módulo fala com API de WhatsApp diretamente —
todos falam com o adapter.

**Drivers:** `evolution` (implementado) · `zapi` (implementado) · `meta`
(interface pronta + conteúdo de aula; implementação fica como extensão). O
driver é **configuração por organização**, não código.

**A assimetria que a interface carrega desde o dia 1:** na API oficial da Meta,
mensagem ativa (iniciada pela empresa fora da janela de 24h de atendimento)
exige **template pré-aprovado**; nas APIs não-oficiais, é texto livre. Por isso
o contrato do adapter distingue os dois casos:

```
POST /canal/enviar
{
  "destinatario":     "+55...",
  "tipo":             "sessao" | "template",
  "template_id":      "...",        // obrigatório quando tipo=template
  "variaveis":        { ... },      // variáveis do template
  "texto":            "...",        // permitido apenas quando tipo=sessao
  "idempotency_key":  "..."
}
```

**Regra de projeto:** lembrete de agenda, confirmação de compromisso e aviso de
cobrança são mensagens **ativas** — logo são modeladas como *template* desde o
início, mesmo rodando em driver não-oficial (que as renderiza como texto livre).
Migrar para a Meta vira troca de driver + aprovação dos templates, **não**
reescrita dos módulos.

- **Inbound:** webhook por driver → normalização → orquestrador/agente. Módulos
  nunca recebem mensagem crua de WhatsApp.
- **Registro:** toda mensagem em `channel_messages` (driver, status
  enviada/entregue/lida/falha, custo quando houver), com retry e idempotência.
- **Risco assumido e comunicado em aula:** drivers não-oficiais violam os termos
  do WhatsApp — o número pode ser bloqueado. Mitigação: número dedicado (nunca o
  pessoal do aluno), e templates prontos para migrar para a Meta quando o volume
  justificar a verificação.

---

## 5. Agent-Friendly por especificação

> **Requisito transversal, não opcional.** Os quatro aplicativos são construídos
> para serem **operados por agentes remotamente**. Um app que só um humano
> consegue usar está incompleto — mesmo que a UI esteja perfeita.

### 5.1 O princípio: API-first, contract-first

Toda capacidade de negócio nasce como **endpoint documentado**, antes de existir
em qualquer tela. A UI e o agente são dois clientes da mesma API, com os mesmos
direitos e as mesmas regras. Se uma ação só existe dentro de um formulário, ela
não existe para o agente — e o módulo não está pronto.

```
   Agente remoto (Claude, ChatGPT, agente próprio, n8n, outro cliente MCP)
                              │  MCP over Streamable HTTP + OAuth 2.1
                              ▼
   ┌──────────────────────────────────────────────────────────┐
   │  4 MCP servers  —  crm · agenda · pedidos · financeiro    │  camada de agente
   │  tools · resources · prompts (schemas + annotations)       │
   └──────────────────────────┬───────────────────────────────┘
                              │  HTTP interno (mesma VPS)
                              ▼
   ┌──────────────────────────────────────────────────────────┐
   │  4 APIs FastAPI  —  OpenAPI é o contrato                  │  camada de domínio
   │  RLS · idempotência · validação · regras de negócio        │
   └──────────────────────────┬───────────────────────────────┘
                              ▼
                      Supabase (Postgres + RLS)
```

**A regra de ouro:** o MCP server é uma **fachada fina**. Nenhuma regra de
negócio mora nele — ele traduz tool call → chamada HTTP e formata a resposta
para consumo de um modelo. Toda validação, todo lock, toda invariante continua
na API e no banco. Assim a UI nunca fica com regras que o agente não tem, e
vice-versa.

### 5.2 Quatro conectores, um por aplicação

| # | MCP server | Endpoint | Escopos OAuth |
|---|---|---|---|
| 01 | `crm-mcp` | `https://mcp.SEU-DOMINIO.com/crm/mcp` | `crm:read` `crm:write` `crm:propose` |
| 02 | `agenda-mcp` | `https://mcp.SEU-DOMINIO.com/agenda/mcp` | `agenda:read` `agenda:write` `agenda:cancel` |
| 03 | `pedidos-mcp` | `https://mcp.SEU-DOMINIO.com/pedidos/mcp` | `pedidos:read` `pedidos:write` `estoque:write` |
| 04 | `financeiro-mcp` | `https://mcp.SEU-DOMINIO.com/financeiro/mcp` | `fin:read` `fin:write` `fin:cobrar` |

**Por que quatro e não um.** Um servidor por domínio permite conceder acesso
parcial (o agente de atendimento recebe agenda + pedidos, nunca financeiro),
isola falhas, e mantém cada catálogo de tools pequeno o suficiente para o modelo
escolher bem. Um servidor monolítico com 40 tools degrada a escolha do agente.

**Convenção de nomes:** `dominio_verbo_objeto` — `crm_mover_etapa`,
`agenda_consultar_slots`, `pedido_confirmar`, `financeiro_projecao_caixa`.
Nome único e previsível dentro do servidor.

### 5.3 Transporte

- **Streamable HTTP** (transporte remoto padrão do MCP). O transporte HTTP+SSE
  antigo está depreciado — não implementar.
- Um único endpoint HTTP por servidor, aceitando `POST` (mensagens do cliente) e
  `GET` (stream de eventos do servidor, quando necessário).
- `stdio` fica disponível apenas para desenvolvimento local do aluno.
- TLS obrigatório. Sem HTTP puro, nem em teste.

### 5.4 Autorização — OAuth 2.1, não API key

Cada MCP server é um **OAuth 2.0 Resource Server**. O Supabase Auth (ou um
provedor dedicado) é o Authorization Server.

**Requisitos:**
1. **Protected Resource Metadata (RFC 9728)** — o servidor publica
   `/.well-known/oauth-protected-resource` apontando para o authorization server.
   É assim que um cliente MCP descobre onde autenticar, sem configuração manual.
2. **Dynamic Client Registration (RFC 7591)** — recomendado, para que um novo
   cliente MCP se registre sozinho em vez de o aluno cadastrar client_id à mão.
3. **PKCE obrigatório** em todo fluxo de autorização.
4. **Resource Indicators (RFC 8707)** — o token é emitido *para aquele servidor*.
   Um token do `financeiro-mcp` não pode ser aceito pelo `pedidos-mcp`.
5. **Proibido token passthrough.** O servidor **rejeita** qualquer token que não
   tenha sido emitido para ele — validar `aud`/resource em toda requisição.
   Aceitar um token de terceiro é a vulnerabilidade clássica (*confused deputy*)
   dessa arquitetura.
6. **Escopos granulares por operação**, conforme a tabela em §5.2. Ler nunca
   exige o mesmo escopo que escrever; cancelar e cobrar têm escopo próprio.
7. O token carrega `org_id` — a **RLS continua sendo a última linha de defesa**.
   Um bug no servidor MCP não pode virar vazamento entre empresas.

**Fase 1 aceitável (aula 1 do módulo 1):** API key estática por aluno
(`Authorization: Bearer <key>`), com escopo por chave e rotação documentada.
**Fase 2 obrigatória até o fim do módulo 4:** OAuth 2.1 completo, com o fluxo
acima. O PRD de cada módulo registra em qual fase o conector está.

> **Nota prática:** servidores MCP hospedados normalmente esperam **bearer token
> OAuth**, não a API key nativa do produto. Quem for conectar esses conectores em
> plataformas de agente (Claude, Managed Agents, etc.) armazena a credencial no
> cofre da plataforma, que faz o refresh automático — o token nunca é colado no
> prompt e nunca entra no sandbox onde o agente roda.

### 5.5 Design de tools — regras que valem para os 4 servidores

**Descrição é interface.** A descrição de uma tool é o que faz o modelo escolher
certo. Mínimo de 3–4 frases, e ela precisa ser **prescritiva sobre quando
chamar**, não apenas sobre o que a tool faz:

> ✅ `"Consulta horários livres para um serviço em um intervalo de datas. Chame
> esta tool sempre que o cliente pedir um horário, mencionar um dia ou período
> ('quinta de tarde'), ou antes de qualquer tentativa de agendar. Não use para
> listar compromissos já marcados — para isso use agenda_meu_dia."*

> ❌ `"Consulta slots."`

**Todo parâmetro tem descrição.** Enums bem nomeados carregam intenção melhor
que texto livre.

**Annotations obrigatórias** em toda tool — é o que permite ao cliente de agente
decidir o que pode rodar sozinho e o que precisa de aprovação:

| Annotation | Quando marcar |
|---|---|
| `readOnlyHint: true` | Tool não altera estado (todas as `*_consultar`, `*_listar`, `*_resumo`) |
| `destructiveHint: true` | Cancelamento, estorno, exclusão |
| `idempotentHint: true` | Repetir a chamada com os mesmos argumentos não duplica efeito |
| `openWorldHint` | `false` — todos os nossos domínios são fechados |

**Saída estruturada.** Toda tool declara `outputSchema` e devolve
`structuredContent` validado, além do texto legível. O agente não deve precisar
parsear prosa para saber o `pedido_id`.

**Idempotência.** Toda tool de escrita aceita `idempotency_key`. Repetir a mesma
chamada devolve o mesmo resultado, sem criar registro novo — o agente vai repetir
chamadas quando a conexão cair, e isso não pode gerar dois pedidos.

**Erros são conversáveis.** Formato único:

```json
{
  "code": "ESTOQUE_INSUFICIENTE",
  "message": "Saldo disponível 2, solicitado 5.",
  "hint": "Diga ao cliente que há apenas 2 unidades e ofereça um substituto com catalogo_sugerir_substituto.",
  "retryable": false
}
```

O `hint` é escrito **para o modelo ler e agir**, não para log.

**Orçamento de tokens.** Resposta de tool entra no contexto do agente e custa
dinheiro a cada turno. Regras:
- Toda listagem é paginada (`limit` padrão 20, `cursor` para a próxima página).
- Devolver sempre IDs — nunca só nomes.
- Nada de dump de tabela: campo que o agente não usa não vai na resposta.
- Resposta acima de ~25k tokens deve virar um **resource** referenciado, não
  texto inline.

### 5.6 Resources e Prompts

**Resources** — leitura por URI, para o agente puxar contexto sem gastar uma tool:

```
crm://oportunidade/{id}          crm://funil/resumo
agenda://dia/{data}              agenda://servicos
pedidos://item/{sku}             pedidos://ruptura
financeiro://caixa/projecao/60   financeiro://cliente/{id}/posicao
```

**Prompts** — playbooks prontos que o usuário dispara por nome no cliente MCP:
`fechamento_do_dia`, `preparar_reuniao`, `revisar_inadimplencia`,
`conferir_estoque_critico`. Cada um vira um workflow multi-tool testado, em vez
de o usuário ter que saber pedir a coisa certa.

### 5.7 Confirmação humana — via elicitation, não via prompt

Ações irreversíveis **não** dependem do agente "lembrar de perguntar". O servidor
MCP usa **elicitation** para solicitar a confirmação ao usuário no meio da
execução, e só então completa a operação.

Exigem confirmação: cancelar compromisso · confirmar pedido · cancelar pedido ·
emitir/ativar contrato · disparar cobrança · marcar oportunidade como ganha/perdida.

Onde o cliente MCP não suportar elicitation, o fallback é o padrão
**propor → confirmar**: a tool devolve uma prévia com `confirmation_token`, e uma
segunda tool `*_confirmar(confirmation_token)` executa. Token expira em 5 minutos.

### 5.8 Auditoria — toda ação de agente é rastreável

Tabela `agent_audit_log` (Supabase), gravada em **toda** chamada de tool:

```sql
create table agent_audit_log (
  id            bigserial primary key,
  org_id        uuid not null,
  mcp_server    text not null,          -- crm | agenda | pedidos | financeiro
  tool_name     text not null,
  client_id     text,                   -- cliente OAuth que chamou
  actor         text,                   -- usuário humano por trás do token
  args_hash     text,                   -- hash dos argumentos (nunca o valor cru)
  resultado     text not null,          -- ok | erro | recusado
  error_code    text,
  latencia_ms   int,
  confirmado_por uuid,                  -- quem aprovou, quando houve confirmação
  created_at    timestamptz default now()
);
```

Todo registro de negócio criado por agente carrega `origem = 'agente'` e o
`client_id`. **Pergunta que o sistema tem que saber responder:** "quem cancelou
esse pedido, o agente ou uma pessoa — e quem autorizou?"

### 5.9 Limites e proteções

| Proteção | Valor |
|---|---|
| Rate limit por credencial | 60 req/min, burst 120 |
| Teto de escrita por credencial | 100 operações de escrita/hora (configurável) |
| Timeout de tool | 30 s (jobs longos devolvem `job_id` e viram assíncronos) |
| Tamanho máximo de resposta | 25k tokens — acima disso, vira resource |
| Tools por servidor | máximo 15 (acima disso o modelo erra a escolha) |
| Escopo de dados | sempre limitado ao `org_id` do token, via RLS |

**Entrada de agente é entrada não confiável.** Texto vindo do agente (que veio do
cliente final) nunca é interpolado em SQL, nunca vira comando, e é validado por
Pydantic antes de tocar o domínio — exatamente como entrada de formulário público.

### 5.10 Testes e aceite do conector

- [ ] Servidor inspecionável com o **MCP Inspector**: tools, resources e prompts
      listados corretamente, com schemas e annotations visíveis
- [ ] Suíte de contrato: toda tool tem teste de sucesso, de erro e de idempotência
- [ ] Teste de autorização: token de outro `org_id` recebe 403 e **não vê dados**
- [ ] Teste de token alheio: token emitido para outro servidor é **rejeitado**
- [ ] Teste de escopo: `crm:read` não consegue executar `crm_mover_etapa`
- [ ] Conector adicionado em **um cliente MCP real** e operado por conversa
- [ ] **Aceite final:** o aluno conecta o servidor de um outro dispositivo, fora
      da rede dele, e opera o sistema inteiro por conversa — com o notebook dele
      desligado

---

## 6. Mapa de leitura

- `01-PRD-CRM.md` — fundação: nuvem, deploy, funil, reuniões, `crm-mcp`
- `02-PRD-Agenda.md` — tempo: grade, lembretes, conversa, `agenda-mcp`
- `03-PRD-Catalogo-Pedidos.md` — venda: estoque, baixa, reposição, `pedidos-mcp`
- `04-PRD-Financeiro-Contratos.md` — dinheiro: contrato, caixa, cobrança, `financeiro-mcp`
