# PRD 02 — Agenda Inteligente
### Sua agenda operada inteiramente por conversa · `agenda-service`

> **Módulo 02 de 04** · Depende de: M1 (Supabase, FastAPI, VPS, padrão de migração)
> **Habilita:** M3 (agendar entrega) e M4 (agendar reunião de cobrança)
> **Stack: canônica** — FastAPI + Supabase + Vite/React em VPS (`00` §3.2)
>
> **Decisões registradas nesta revisão:** o **`canal-service` nasce neste
> módulo** (adapter WhatsApp com drivers Evolution + Z-API implementados e Meta
> como interface/aula — `00` §4.8) · integração de calendário é **feed .ics
> somente-leitura** (RF-11); sincronização bidirecional fica explicitamente fora.

---

## 1. Problema

A agenda vive em três lugares ao mesmo tempo: WhatsApp, papel e memória. Marcar
exige abrir calendário; remarcar exige lembrar quem avisar; cancelar deixa o
horário morto porque ninguém devolveu ele para a grade. E o cliente falta porque
ninguém lembrou.

## 2. Contexto de mercado — o que os líderes fazem, e o que adotamos

Referências: Calendly e Cal.com (agendamento), Google Appointment Schedules, e
os verticais brasileiros de serviço (Trinks, Booksy). O inventário honesto:

| Prática de mercado | Referência | Adotamos? | Onde |
|---|---|---|---|
| Slots calculados com duração + buffers + antecedência mínima | Calendly | ✅ | RF-02 |
| Granularidade de exibição de horários configurável | Calendly | ✅ (padrão 30 min) | RF-02 |
| Lembretes multi-toque (24h + 2h) para reduzir no-show | todos | ✅ — com números do efeito medidos no próprio sistema | RF-05 |
| Confirmação por resposta direta do cliente ("confirmo") | Booksy | ✅ via canal WhatsApp | RF-05, §8 IA-04 |
| Política de antecedência para cancelar/remarcar | todos | ✅ configurável | RF-06 |
| Registro e histórico de no-show por cliente | Booksy | ✅ | RF-06, §8 IA-03 |
| Feed de calendário (.ics) para ver tudo no Google/Apple | Calendly | ✅ somente-leitura | RF-11 |
| **Link público de auto-agendamento** | Calendly (o produto inteiro) | ⚠️ **substituído por conversa** — a tese do módulo é o agente, não o formulário | RF-03 |
| Sincronização bidirecional Google/Outlook | Calendly, Cal.com | ❌ decisão registrada — OAuth + webhooks + resolução de conflito consumiriam o módulo | §6.2 |
| Reserva temporária de slot durante a escolha (hold) | Calendly | ❌ v1 — conflito na confirmação é tratado com alternativas; hold adiciona estado que expira | §6.2 |
| Pagamento/caução no agendamento (anti no-show) | Calendly + Stripe | ❌ — gateway com liquidação está fora do programa | `00` §4.7 |
| Fila de espera automática | Booksy | ❌ v1 | §6.2 |

## 3. Objetivo

Uma agenda que se opera **por conversa**: marcar, remarcar, confirmar e cancelar
sem abrir calendário. O horário cancelado volta para a grade na hora. O lembrete
dispara sozinho — inclusive com o aluno offline — pelo **canal de WhatsApp que
este módulo constrói e os módulos 3 e 4 reutilizam**. E todo compromisso aparece
também no Gestor de Tarefas e no calendário pessoal (feed .ics): uma agenda,
três visões, zero retrabalho.

## 4. Métricas de sucesso

| Métrica | Alvo |
|---|---|
| Agendamentos feitos 100% por conversa | ≥ 90% |
| Double-booking | **0** (garantido no banco) |
| No-show após lembrete ativo | queda ≥ 30% vs. baseline |
| Horário liberado após cancelamento | < 5 s |
| Lembretes disparados com máquina do aluno desligada | 100% |
| Entrega de mensagens do canal (enviada → entregue) | ≥ 98% |
| Opt-out do canal de mensagens | < 5% dos clientes ativos |
| Troca de driver do canal (Evolution ↔ Z-API) | por configuração, zero mudança de código |

## 5. Personas e jornadas

| Persona | Job to be done | Como usa |
|---|---|---|
| **Cliente final** | "Marcar sem baixar app, no WhatsApp, na hora que lembrei" | Manda mensagem em linguagem natural; recebe lembrete; responde "confirmo" |
| **Prestador / atendente** | "Ver o dia, bloquear férias, saber quem confirmou" | Consulta o dia (UI ou agente); bloqueia grade; acompanha no Google via .ics |
| **Dono** | "Menos buraco na agenda, menos falta" | Métricas de ocupação e no-show; cobra política de confirmação |
| **Agente de IA** | Usuário de primeira classe: entende o pedido, checa grade, marca, lembra, remarca | Via `agenda-mcp` (§13) + canal inbound (§9.1) |

**Jornada mestra:** cliente manda mensagem (§9.1) → agente entende a intenção e
a data (§8 IA-01/IA-04) → consulta slots (RF-02/03) → marca sem double-booking
(RF-04) → confirmação + lembretes via template (RF-05) → cliente confirma ou
remarca por resposta (RF-06) → tarefa espelho (RF-07) e feed .ics (RF-11)
refletem tudo.

---

## 6. Escopo

### 6.1 Dentro
1. Cadastro de serviços (preço, duração, recursos)
2. Grade de disponibilidade (horário de trabalho, intervalos, bloqueios)
3. Agendamento por conversa (linguagem natural → slot)
4. **`canal-service`**: adapter WhatsApp (Evolution + Z-API; Meta como
   interface/aula), templates, inbound, opt-out — nasce aqui, serve M3 e M4
5. Confirmações e lembretes automáticos pelo canal
6. Reagendamento e cancelamento com devolução do slot
7. Espelho no Gestor de Tarefas
8. Feed .ics somente-leitura por recurso (Google/Apple Calendar)
9. Migração da agenda existente para a nuvem, com histórico preservado

### 6.2 Fora
Sincronização bidirecional Google/Outlook (**decisão registrada** — fica como
extensão pós-programa) · hold temporário de slot · pagamento no ato (gateway
fora do programa) · fila de espera automática · videochamada · link público de
auto-agendamento (a conversa é a interface).

---

## 7. Requisitos funcionais

### RF-01 — Serviços, preços e duração
**Critérios de aceite**
- Serviço tem: nome, duração (min), preço, buffer antes/depois, ativo/inativo.
- Serviço pode exigir **recurso** (profissional, sala, equipamento).
- Alterar duração **não** altera agendamentos já existentes.
- Preço aqui é a referência que o M4 usa para gerar a receita.

### RF-02 — Grade de disponibilidade
**Critérios de aceite**
- Horário de trabalho por dia da semana, por recurso.
- Bloqueios pontuais (feriado, almoço, férias) com motivo.
- `GET /slots?servico=&data=` devolve apenas horários **realmente livres**,
  já descontando duração + buffers + bloqueios + agendamentos.
- Granularidade de exibição configurável (padrão: passos de 30 min).
- Antecedência mínima e janela máxima de agendamento configuráveis.

### RF-03 — Agendamento por conversa
**Critérios de aceite**
- O agente interpreta "quinta de tarde", "amanhã cedo", "semana que vem" e
  converte em intervalo de busca (timezone America/Sao_Paulo) — técnica e
  salvaguardas em §8 IA-01.
- Se o horário pedido está ocupado, o agente **oferece as 3 alternativas mais
  próximas** — nunca responde só "indisponível".
- Confirmação exige: serviço + horário + cliente identificado (nome + telefone).
  Faltando um, o agente pergunta; não inventa.
- Cliente não precisa existir no CRM: a agenda guarda nome/telefone
  denormalizados e vincula ao CRM quando houver correspondência.
- Sem formulário, sem link, sem fricção — a conversa é a interface.

### RF-04 — Zero double-booking (invariante do sistema)
**Critérios de aceite**
- Garantia no **banco**, não na aplicação: constraint de exclusão por
  intervalo + recurso (`EXCLUDE USING gist`).
- Teste: 10 requisições simultâneas para o mesmo slot → 1 sucesso, 9 recusas
  com erro legível e alternativas no payload.

### RF-05 — Confirmações e lembretes (via canal)
**Critérios de aceite**
- Régua configurável (padrão: confirmação imediata, lembrete 24h e 2h antes).
- **Toda mensagem ativa é um template do canal** (`00` §4.8) — nunca texto
  montado ad-hoc no código da agenda.
- Job roda no VPS: **dispara com a máquina do aluno desligada**.
- Resposta do cliente ("confirmo" / "não vou poder") atualiza o status pelo
  agente (§8 IA-04).
- Sem duplicidade: cada lembrete é enviado uma única vez (registro em
  `reminders` + idempotência no canal).
- Falha de envio agenda retry (3 tentativas) e, esgotado, cria tarefa manual.
- **Opt-out respeitado sempre:** cliente que pediu para sair não recebe nenhuma
  mensagem ativa (§9.1) — o lembrete morre com log, e uma tarefa avisa o humano.

### RF-06 — Reagendar e cancelar
**Critérios de aceite**
- Cancelamento **libera o slot imediatamente** para novos agendamentos.
- Reagendamento é atômico: ou o novo horário é reservado e o antigo liberado,
  ou nada muda (sem estado intermediário com o cliente sem horário).
- Toda mudança grava histórico com origem (`cliente`, `agente`, `humano`) e motivo.
- Cancelamento exige **confirmação humana** quando disparado pelo agente.
- Política de antecedência mínima para cancelar/remarcar é configurável; fora
  da política, o agente explica a regra e encaminha ao humano.
- Falta é registrada como `no_show` — alimenta o histórico do cliente (IA-03).

### RF-07 — Espelho no Gestor de Tarefas
**Critérios de aceite**
- Todo compromisso confirmado cria/atualiza uma tarefa correspondente.
- Cancelar o compromisso cancela a tarefa espelho.
- O espelho é **derivado**: a agenda é a fonte da verdade; conflito resolve a favor
  da agenda.
- Falha na integração não bloqueia o agendamento — entra em fila de retry.

### RF-08 — Migração para a nuvem
Mesmo roteiro do M1 (§4.5 do doc base), aplicado à agenda.
**Critérios de aceite:** histórico inteiro preservado, agendamentos futuros
reconciliados 1:1, nenhum compromisso futuro perdido ou duplicado.

### RF-09 — Tools do agente
Definidas no conector MCP (§13). Resumo: 7 tools, escopos `agenda:read` /
`agenda:write` / `agenda:cancel`, cancelamento atrás de confirmação humana.

### RF-10 — `canal-service` (nasce neste módulo; contrato em `00` §4.8)
**Critérios de aceite**
- Drivers `evolution` e `zapi` **implementados**; driver `meta` com interface
  pronta e implementação documentada como extensão (conteúdo de aula).
- Driver é configuração por organização — **trocar de driver não muda uma linha
  dos módulos** (teste de aceite: mesma suíte passa nos dois drivers).
- `POST /canal/enviar` distingue `tipo: sessao | template`; mensagens ativas
  **recusam** `tipo: sessao` (erro claro) — a regra template-first vale desde já.
- Templates com variáveis (`{{nome}}`, `{{servico}}`, `{{data_hora}}`,
  `{{profissional}}`) cadastrados e versionados; sementes: confirmação,
  lembrete 24h, lembrete 2h, reagendamento, cancelamento, aviso de cobrança
  (este último já preparado para o M4).
- Inbound: webhook por driver → normalização (`org, telefone, texto,
  message_id, timestamp`) → orquestrador/agente. Idempotência por
  `(driver, message_id)` — reentrega não duplica conversa.
- Toda mensagem em `channel_messages` com direção, status
  (enviada/entregue/lida/falha), driver, custo (quando houver) e erro.
- **Opt-out:** resposta "SAIR" (e variações) registra `channel_optouts`
  automaticamente e responde confirmando a saída; qualquer envio ativo consulta
  a lista antes.
- Número de WhatsApp **dedicado** por organização — o produto recusa configurar
  o número pessoal do aluno (checagem + aviso em aula).

### RF-11 — Feed .ics somente-leitura (decisão registrada)
**Critérios de aceite**
- URL por recurso com token: `GET /ics/{token}.ics` — assinável no Google
  Calendar e Apple Calendar.
- Token revogável e regenerável (vazou o link → revoga, gera outro).
- Eventos com timezone correto (`America/Sao_Paulo`), título com serviço +
  cliente (configurável: modo privado só mostra "ocupado").
- Compromisso cancelado sai do feed na próxima leitura.
- **Expectativa gerenciada em aula:** o Google atualiza calendários assinados
  em ciclos longos (horas, não controlamos). O feed é visão consolidada, não
  notificação em tempo real — lembrete em tempo real é papel do canal (RF-05).

---

## 8. Recursos de IA

> **Nota de arquitetura (e de aula):** este módulo ensina o **segundo padrão de
> IA** do programa. No M1, a IA mora *dentro do serviço* (o CRM chama LLM para
> resumir reunião). Aqui, a IA mora **no agente**: o `agenda-service` quase não
> chama LLM — ele oferece contratos amigáveis a agente (slots com alternativas,
> erros com `hint`, datas com `label_humano`) e quem pensa é o orquestrador via
> MCP. Os dois padrões são legítimos; saber escolher entre eles é o conteúdo.
> O gradiente de risco do programa continua valendo: reversível → automático;
> negócio → proposto; irreversível (cancelar) → confirmação humana.

### IA-01 — Interpretação de datas em linguagem natural

| | |
|---|---|
| **Onde vive** | No agente (prompt + descrição da tool `agenda_consultar_slots`) |
| **Entrada** | Expressão do cliente: "quinta de tarde", "amanhã cedo", "daqui a 15 dias" |
| **Técnica** | O LLM converte para intervalo ISO 8601 **com offset**; a API valida formato e rejeita ambiguidade (ex.: data no passado) |
| **Salvaguarda** | Antes de confirmar, o agente **repete a data por extenso** ("quinta, 14 de maio, 15h30") — o `label_humano` vem pronto da API para impedir reformatação errada |
| **Fallback** | Ambiguidade real ("dia 8" — que mês?) → pergunta; **nunca chuta** |
| **Teste** | Tabela de expressões brasileiras com resultado esperado, rodada contra o agente em CI de prompt |

### IA-02 — Redação de templates e respostas

| | |
|---|---|
| **Mensagem ativa** | O texto do template é redigido **uma vez** com ajuda da IA, revisado e aprovado pelo humano, e versionado no canal — a IA não improvisa mensagem ativa por cliente (regra template-first) |
| **Mensagem de sessão** | Dentro de uma conversa aberta (cliente escreveu), o agente redige livremente — tom definido no prompt da organização |
| **Fallback** | Sem template aprovado para um evento → mensagem não sai + tarefa para o humano |

### IA-03 — Risco de no-show *(determinístico e explicável)*

| | |
|---|---|
| **Técnica** | v1 **sem ML** — pontos por: histórico de faltas do cliente, antecedência da marcação, primeira visita, horário (mesma honestidade do scoring do M1: com pouco dado, ML é teatro) |
| **Saída** | `risco_no_show` (baixo/médio/alto) + composição visível |
| **Efeito** | Risco alto → lembrete extra com pedido de confirmação explícito (template próprio); nunca cancela sozinho |
| **Gatilho** | Calculado ao agendar e recalculado no lembrete de 24h |

### IA-04 — Interpretação da resposta do cliente (inbound)

| | |
|---|---|
| **Entrada** | Resposta livre no WhatsApp: "confirmo", "não vou poder", "dá pra ser 16h?", "quem fala?" |
| **Técnica** | O agente classifica a intenção (confirmar / cancelar / remarcar / dúvida / opt-out / fora de contexto) e age via tools MCP |
| **Salvaguarda** | Cancelamento e remarcação seguem exigindo os fluxos com confirmação (RF-06) — a classificação de intenção **não** pula as regras |
| **Fallback** | Intenção não reconhecida com confiança → agente responde pedindo esclarecimento; na segunda falha, encaminha ao humano (tarefa + a conversa fica marcada "aguardando humano") |
| **Opt-out** | "SAIR" e variações são detectadas **antes** do LLM, por regra determinística no canal (RF-10) — sair do spam não pode depender de IA acertar |

---

## 9. Integrações externas (API autenticada)

> Padrão de webhook do programa (M1 §9): responder 2xx rápido, processar
> assíncrono, idempotência por ID de evento, segredo verificado, replay tolerado.
> Segredos por organização cifrados, write-only, nunca em log.

### 9.1 WhatsApp via `canal-service` — 3 drivers

| | Evolution API | Z-API | Meta Cloud API |
|---|---|---|---|
| **Status no programa** | ✅ implementado | ✅ implementado | interface + aula (extensão guiada) |
| **Auth** | apikey da instância self-host | client-token da instância | token de app + verificação de negócio |
| **Custo** | zero (roda no próprio VPS) | assinatura por instância | por conversa/template (tabela Meta) |
| **Mensagem ativa** | texto livre (template renderizado) | texto livre (template renderizado) | **template pré-aprovado obrigatório** |
| **Risco** | não-oficial — banimento possível | não-oficial — banimento possível | oficial, sem risco de ToS |
| **Webhook inbound** | por instância → `/webhooks/canal/evolution` | → `/webhooks/canal/zapi` | → `/webhooks/canal/meta` |

Aula prática: Evolution self-host no VPS (custo zero, QR code ao vivo) + Z-API
como segunda instância para **demonstrar a troca de driver por configuração**.
Meta entra como aula: verificação, templates, tabela de preços — e por que o
sistema já está pronto para ela (template-first).

### 9.2 Feed .ics (RF-11)
Sem OAuth — o segredo é o token na URL, revogável. Conteúdo mínimo, modo
privado disponível. Não é canal de notificação (expectativa em aula).

### 9.3 `tasks-service` (espelho de tarefas)
Service-to-service com credencial própria e escopo mínimo (criar/atualizar/
cancelar tarefa). Retry com backoff; reconciliação diária (RF-07).

### 9.4 CRM (`crm-service`, M1)
Leitura para vincular cliente do agendamento a empresa/contato existente
(por telefone). Sem vínculo, a agenda opera sozinha com os dados denormalizados
— **a dependência é opcional em runtime**, obrigatória só na demo integrada.

---

## 10. Modelo de dados (Supabase)

```sql
create extension if not exists btree_gist;

create table services (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  nome text not null,
  duracao_min int not null check (duracao_min > 0),
  preco numeric(14,2) not null default 0,
  buffer_antes_min int default 0, buffer_depois_min int default 0,
  ativo boolean default true,
  created_at timestamptz default now()
);

create table resources (              -- profissional, sala, equipamento
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null, nome text not null, tipo text, ativo boolean default true
);

create table service_resources (
  service_id uuid references services(id), resource_id uuid references resources(id),
  primary key (service_id, resource_id)
);

create table availability_rules (     -- grade semanal
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  resource_id uuid references resources(id),
  dia_semana int not null check (dia_semana between 0 and 6),
  hora_inicio time not null, hora_fim time not null,
  check (hora_fim > hora_inicio)
);

create table availability_blocks (    -- férias, feriado, almoço
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  resource_id uuid references resources(id),
  periodo tstzrange not null,
  motivo text
);

create table appointments (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  service_id uuid not null references services(id),
  resource_id uuid not null references resources(id),
  company_id uuid,                    -- vínculo CRM (opcional)
  contact_id uuid,                    -- vínculo CRM (opcional)
  cliente_nome text not null,        -- denormalizado: agenda opera sem CRM
  cliente_telefone text not null,
  periodo tstzrange not null,
  status text not null default 'agendado',   -- agendado|confirmado|cancelado|realizado|no_show
  risco_no_show text,                 -- baixo|medio|alto (IA-03)
  risco_detalhe jsonb,
  origem text default 'agente',
  observacoes text,
  task_id uuid,                       -- espelho no Gestor de Tarefas
  created_at timestamptz default now(), updated_at timestamptz default now(),

  -- RF-04: double-booking impossível no banco
  exclude using gist (
    resource_id with =,
    periodo with &&
  ) where (status in ('agendado','confirmado'))
);

create table appointment_history (
  id bigserial primary key,
  appointment_id uuid references appointments(id),
  acao text not null,                 -- criado|reagendado|cancelado|confirmado|no_show
  de tstzrange, para tstzrange,
  origem text, motivo text, por uuid,
  em timestamptz default now()
);

create table reminders (
  id bigserial primary key,
  org_id uuid not null,
  appointment_id uuid not null references appointments(id),
  tipo text not null,                 -- confirmacao|lembrete_24h|lembrete_2h|risco_alto
  agendado_para timestamptz not null,
  enviado_em timestamptz,
  canal_message_id bigint,            -- rastreio no canal
  tentativas int default 0, erro text,
  unique (appointment_id, tipo)       -- sem lembrete duplicado
);

create table ics_tokens (             -- RF-11
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  resource_id uuid references resources(id),
  token text not null unique,
  modo text not null default 'completo',   -- completo|privado
  revogado_em timestamptz,
  created_at timestamptz default now()
);
```

**Schema do `canal-service`** (serviço próprio, mesmo VPS — contrato em `00` §4.8):

```sql
create table channel_configs (        -- driver é configuração por org
  org_id uuid primary key,
  driver text not null check (driver in ('evolution','zapi','meta')),
  credenciais jsonb not null,         -- cifrado na aplicação; write-only na API
  numero text not null,               -- número dedicado (nunca o pessoal)
  ativo boolean default true
);

create table channel_templates (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  nome text not null,                 -- lembrete_24h, confirmacao, ...
  corpo text not null,                -- com {{variaveis}}
  versao int not null default 1,
  aprovado_meta boolean default false,-- pronto p/ migração ao driver oficial
  ativo boolean default true,
  unique (org_id, nome, versao)
);

create table channel_messages (
  id bigserial primary key,
  org_id uuid not null,
  direcao text not null check (direcao in ('saida','entrada')),
  telefone text not null,
  tipo text check (tipo in ('sessao','template')),
  template_id uuid,
  corpo_renderizado text,
  driver text not null,
  driver_message_id text,             -- idempotência inbound
  status text not null default 'pendente', -- pendente|enviada|entregue|lida|falha
  custo numeric(10,4),
  erro text,
  idempotency_key text,
  created_at timestamptz default now(),
  unique (driver, driver_message_id)
);

create table channel_optouts (
  org_id uuid not null,
  telefone text not null,
  origem text,                        -- palavra-chave|pedido_humano
  em timestamptz default now(),
  primary key (org_id, telefone)
);
```

**Índices:** `appointments(org_id, resource_id)` · `appointments using gist (periodo)` ·
`appointments(org_id, cliente_telefone)` · `reminders(agendado_para) where enviado_em is null` ·
`channel_messages(org_id, telefone, created_at desc)`.

---

## 11. API (principais rotas)

```
# agenda-service
GET  /services                        POST /services
GET  /resources                       POST /availability/rules
POST /availability/blocks
GET  /slots?service_id=&from=&to=     # motor de disponibilidade
POST /appointments                    { service_id, inicio, cliente_nome, cliente_telefone }
POST /appointments/{id}/reschedule    { novo_inicio }     # atômico
POST /appointments/{id}/cancel        { motivo }
POST /appointments/{id}/confirm       POST /appointments/{id}/no-show
GET  /appointments?date=&resource=
GET  /agenda/day?date=                # visão narrada para o agente
GET  /ics/{token}.ics                 # RF-11 (público, token revogável)
POST /ics/tokens                      POST /ics/tokens/{id}/revogar

# canal-service (contrato em 00 §4.8)
POST /canal/enviar                    # sessao|template — template-first
GET  /canal/templates                 POST /canal/templates
GET  /canal/mensagens?telefone=
POST /webhooks/canal/evolution        POST /webhooks/canal/zapi
POST /webhooks/canal/meta             # pronto para a extensão
```

Autorização por escopo em toda rota; `canal-service` só aceita chamadas dos
serviços do programa (credencial service-to-service) — nunca do navegador.

---

## 12. Requisitos não funcionais

- **Consistência:** `EXCLUDE USING gist` é inegociável — a regra vive no banco.
- **Timezone:** cálculo de slot sempre em America/Sao_Paulo, persistência em UTC
  (`tstzrange`); suíte de testes de borda de horário de verão (o Brasil não tem
  DST hoje, mas a regra pode voltar — o teste fica).
- **Job de lembretes:** roda a cada 5 min no VPS; janela de tolerância de 15 min;
  idempotente (o `unique` em `reminders` impede reenvio).
- **Latência:** `GET /slots` para 30 dias em < 400 ms (p95).
- **Resiliência:** driver de canal fora do ar não perde lembrete — fila com
  retry; esgotado, tarefa manual. Trocar de driver não perde mensagens em fila.
- **LGPD (telefone e histórico de conversa do cliente final):**
  - Telefone é dado pessoal: coleta mínima, finalidade declarada (agendamento e
    lembretes), sem uso para marketing sem consentimento separado.
  - **Opt-out é imediato e determinístico** (RF-10) — não depende de IA.
  - Pedido de eliminação: anonimização efetiva (nome/telefone sobrescritos no
    histórico; compromissos futuros cancelados com aviso ao humano).
  - Conversas retidas 12 meses (configurável); credenciais de driver cifradas.
- **Segurança:** RLS por `org_id` em todas as tabelas (canal incluído);
  rate limit por credencial; webhook com segredo por driver.

---

## 13. Conector MCP — `agenda-mcp`

> Requisitos transversais em `00-ARQUITETURA-BASE.md` §5. Repete o padrão
> estabelecido pelo `crm-mcp` no módulo 1.

**Endpoint:** `https://mcp.SEU-DOMINIO.com/agenda/mcp` · Streamable HTTP
**Escopos:** `agenda:read` · `agenda:write` · `agenda:cancel`
**Fase de auth:** já nasce em fase 2 (OAuth 2.1) — o padrão veio pronto do M1

> **Este é o conector mais exposto do programa.** É ele que o cliente final
> aciona, indiretamente, ao mandar mensagem. Escopo apertado e confirmação de
> cancelamento não são detalhes.

### 13.1 Tools

| Tool | Escopo | `readOnly` | `destructive` | `idempotent` | Confirmação |
|---|---|:---:|:---:|:---:|---|
| `agenda_listar_servicos` | `agenda:read` | ✅ | — | ✅ | — |
| `agenda_consultar_slots` | `agenda:read` | ✅ | — | ✅ | — |
| `agenda_meu_dia` | `agenda:read` | ✅ | — | ✅ | — |
| `agenda_agendar` | `agenda:write` | — | — | ✅ | — |
| `agenda_reagendar` | `agenda:write` | — | — | ✅ | — |
| `agenda_confirmar` | `agenda:write` | — | — | ✅ | — |
| `agenda_cancelar` | `agenda:cancel` | — | ✅ | ✅ | **sim** |

**Descrição de referência** — a tool mais chamada do sistema:

```jsonc
{
  "name": "agenda_consultar_slots",
  "description":
    "Retorna os horários realmente livres para um serviço num intervalo de datas, já \
descontando duração, buffers, bloqueios e compromissos existentes. Chame SEMPRE antes \
de tentar agendar, e sempre que o cliente mencionar um dia, período ou intenção de \
horário ('quinta de tarde', 'amanhã cedo', 'semana que vem'). Converta a expressão em \
um intervalo de datas no fuso America/Sao_Paulo antes de chamar. Se o retorno vier \
vazio, não responda apenas 'indisponível' — amplie o intervalo e ofereça as 3 \
alternativas mais próximas. Não use para ver compromissos já marcados (use agenda_meu_dia).",
  "inputSchema": {
    "type": "object",
    "properties": {
      "service_id": { "type": "string", "format": "uuid",
        "description": "Serviço desejado. Obtenha com agenda_listar_servicos." },
      "from": { "type": "string", "format": "date-time",
        "description": "Início do intervalo de busca, ISO 8601 com offset." },
      "to":   { "type": "string", "format": "date-time" },
      "resource_id": { "type": "string", "format": "uuid",
        "description": "Opcional. Profissional ou sala específica, se o cliente pediu." },
      "limit": { "type": "integer", "default": 20, "maximum": 50 }
    },
    "required": ["service_id", "from", "to"],
    "additionalProperties": false
  },
  "annotations": {
    "readOnlyHint": true, "destructiveHint": false,
    "idempotentHint": true, "openWorldHint": false
  }
}
```

**Critérios de aceite específicos**
- Toda saída de horário é **ISO 8601 com offset explícito** (`-03:00`), nunca
  string local ambígua. A tool devolve também `label_humano`
  (`"quinta, 14 de maio, 15h30"`) para o agente falar sem reformatar.
- `agenda_agendar` recusa slot ocupado com
  `{code: "SLOT_INDISPONIVEL", hint: "Ofereça estas alternativas: ..."}` já
  trazendo 3 alternativas no payload do erro — o agente não precisa de uma
  segunda chamada para se recuperar.
- `agenda_reagendar` é **atômica na tool**: ou devolve o novo compromisso e o
  slot antigo já liberado, ou não muda nada. Nunca existe estado intermediário
  visível ao agente.
- `agenda_cancelar` usa **elicitation** para confirmar antes de executar. Sem
  suporte a elicitation no cliente, cai no padrão `confirmation_token`
  (prévia → `agenda_cancelar(confirmation_token)`), com expiração em 5 minutos.
- `agenda_consultar_slots` responde em < 400 ms (p95) para janela de 30 dias.

### 13.2 Resources

| URI | Conteúdo |
|---|---|
| `agenda://servicos` | Serviços ativos com preço, duração e buffers |
| `agenda://recursos` | Profissionais, salas e equipamentos ativos |
| `agenda://dia/{data}` | Agenda completa do dia, em linguagem clara |
| `agenda://compromisso/{id}` | Ficha do compromisso + histórico de alterações |
| `agenda://grade/{recurso_id}` | Horário de trabalho e bloqueios vigentes |

### 13.3 Prompts

| Prompt | O que faz |
|---|---|
| `agenda_do_dia` | Lê a agenda de hoje, destaca conflitos, faltas prováveis e buracos |
| `remarcar_semana` | Dado um bloqueio novo (férias, imprevisto), lista os afetados e propõe realocação |
| `confirmar_pendentes` | Lista compromissos das próximas 24h sem confirmação e prepara as mensagens |

### 13.4 Aceite do conector
- [ ] Servidor inspecionável no MCP Inspector com schemas e annotations corretos
- [ ] `agenda_cancelar` marcada com `destructiveHint: true` e bloqueada sem
      confirmação humana
- [ ] Credencial com `agenda:read` + `agenda:write` **não** consegue cancelar
- [ ] 10 chamadas simultâneas de `agenda_agendar` no mesmo slot → 1 sucesso,
      9 erros legíveis com alternativas
- [ ] Teste de borda de horário de verão não produz slot fantasma nem buraco
- [ ] Marcar, reagendar e confirmar por conversa, de outro dispositivo, com o
      notebook do aluno desligado

---

## 14. Demo final do módulo (critério de conclusão)

> **Marcar, reagendar e confirmar um horário inteiramente por conversa — no
> WhatsApp de verdade.**

**Roteiro executável ao vivo:**
1. Cliente manda **WhatsApp real** ("Quero marcar um corte quinta de tarde") →
   webhook inbound chega no VPS → agente consulta a grade e **oferece 3
   horários** com data por extenso.
2. Cliente escolhe → compromisso criado + confirmação por **template** enviada +
   tarefa espelho no Gestor de Tarefas + o horário aparece no **Google Calendar
   do aluno** (feed .ics).
3. "Preciso mudar para sexta" → reagendamento atômico: quinta volta para a grade
   na hora (demonstrado consultando `/slots` na frente da turma).
4. Lembrete de 24h dispara pelo job do VPS — **com o notebook do aluno
   desligado** — e chega no celular do "cliente".
5. Cliente responde "confirmo" → IA-04 classifica → status atualizado.
6. **Troca de driver ao vivo:** configuração muda de Evolution para Z-API e o
   mesmo fluxo roda — zero mudança de código.

Se qualquer passo exigir abrir um sistema manualmente, o módulo não está concluído.

---

## 15. Riscos

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Double-booking em concorrência | Média | Alto | Constraint GiST + teste de 10 requisições simultâneas |
| Erro de fuso/horário de verão | Média | Alto | `tstzrange` + suíte de testes de borda |
| Agente interpreta data errada | Alta | Médio | Repetir data por extenso + `label_humano` pronto da API |
| **Número banido pelo WhatsApp (driver não-oficial)** | Média | Alto | Número dedicado; templates prontos para migrar à Meta; risco dito em aula, não descoberto |
| Lembrete duplicado irrita cliente | Média | Médio | `unique(appointment_id, tipo)` + idempotência no canal |
| Mensagem ativa vira spam (denúncia) | Média | Alto | Template-first + opt-out determinístico + régua moderada por padrão |
| Cliente responde e ninguém trata (IA não entende) | Média | Médio | Fallback em duas etapas → fila "aguardando humano" com tarefa |
| Espelho de tarefas dessincroniza | Média | Baixo | Agenda é fonte da verdade + reconciliação diária |
| Aluno espera .ics em tempo real | Alta | Baixo | Expectativa dita em aula: feed é visão, canal é notificação |

## 16. Plano de entrega

| Etapa | Entrega |
|---|---|
| 1 | Schema + migração da agenda para Supabase (reconciliada) |
| 2 | Serviços, recursos e grade de disponibilidade |
| 3 | Motor de slots (`GET /slots`) + constraint anti-double-booking |
| 4 | Agendamento, reagendamento atômico e cancelamento |
| 5 | **`canal-service`**: drivers Evolution + Z-API, templates, inbound, opt-out |
| 6 | Job de lembretes via canal + espelho no Gestor de Tarefas |
| 7 | Feed .ics por recurso (tokens revogáveis) |
| 8 | **Conector MCP `agenda-mcp`** (§13) + linguagem natural de datas + **demo final** |
