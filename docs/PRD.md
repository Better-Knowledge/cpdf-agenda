# PRD 02 — Agenda Inteligente
### Sua agenda operada inteiramente por conversa · `agenda-service`

> **Módulo 02 de 04** · Depende de: M1 (Supabase, FastAPI, VPS, padrão de migração)
> **Habilita:** M3 (agendar entrega) e M4 (agendar reunião de cobrança)
> **Stack: canônica** — FastAPI + Supabase + Vite/React em VPS (`00` §3.2)
>
> **Decisões registradas nesta revisão:** o **`canal-service` nasce neste
> módulo** (adapter WhatsApp com drivers Evolution + Z-API implementados e Meta
> como interface/aula — `00` §4.8; API oficial da Meta no roadmap §18) ·
> **Google Calendar é a integração-base de calendário** (RF-12): push via API +
> leitura de ocupado (busy-read), com OAuth; sincronização bidirecional completa
> fica no roadmap; o feed .ics (RF-11) permanece como opção sem OAuth ·
> **link público de auto-agendamento volta como opcional** (RF-13) — a conversa
> segue sendo a interface principal · **Calendly é a única integração de booking
> externo nesta etapa**, opcional e one-way (RF-16) · a documentação **OpenAPI é
> servida por Scalar** (RF-17) e é o contrato que o `agenda-mcp` consome.

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
| Feed de calendário (.ics) para ver tudo no Google/Apple | Calendly | ✅ somente-leitura, para quem não conectar OAuth | RF-11 |
| Integração Google Calendar (evento aparece na hora) | Calendly, Cal.com | ✅ **push via API + busy-read** — a base de integração, porque é o calendário que a maioria dos alunos já usa | RF-12 |
| **Link público de auto-agendamento** | Calendly (o produto inteiro) | ✅ **opcional** — a conversa segue sendo a via principal (tese do módulo); o link atende o cliente que prefere clicar | RF-13 |
| Sincronização bidirecional Google/Outlook | Calendly, Cal.com | ⚠️ parcial — push + busy-read neste módulo; bidirecional completa (editar no Google reflete na agenda) no roadmap | RF-12, §18 |
| Reserva temporária de slot durante a escolha (hold) | Calendly | ❌ v1 — conflito na confirmação é tratado com alternativas; hold adiciona estado que expira | §18 |
| Pagamento/caução no agendamento (anti no-show) | Calendly + Stripe | ⚠️ roadmap — o link público já nasce com a configuração de caução (desligada por padrão); a cobrança via Pix vem depois | RF-13, §18 |
| Fila de espera automática | Booksy | ✅ — sinergia direta com o canal: cancelou, o próximo recebe WhatsApp | RF-14 |
| Compromissos recorrentes (toda terça às 10h) | Trinks, Booksy | ✅ recorrência simples; pacotes de sessões no roadmap | RF-15, §18 |
| Importar agendamentos de plataforma externa | Cal.com | ✅ **Calendly, opcional e one-way** — só o Calendly nesta etapa, para simplificar | RF-16 |

## 3. Objetivo

Uma agenda que se opera **por conversa**: marcar, remarcar, confirmar e cancelar
sem abrir calendário. O horário cancelado volta para a grade na hora. O lembrete
dispara sozinho — inclusive com o aluno offline — pelo **canal de WhatsApp que
este módulo constrói e os módulos 3 e 4 reutilizam**. E todo compromisso aparece
também no Gestor de Tarefas e **no Google Calendar do prestador, na hora**
(push via API — RF-12; feed .ics para quem não conectar): uma agenda, três
visões, zero retrabalho.

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
| Compromisso visível no Google Calendar após criação (push) | < 60 s |
| Slot cancelado ofertado ao primeiro da fila de espera | < 5 min |

## 5. Personas e jornadas

| Persona | Job to be done | Como usa |
|---|---|---|
| **Cliente final** | "Marcar sem baixar app, no WhatsApp, na hora que lembrei" | Manda mensagem em linguagem natural; recebe lembrete; responde "confirmo" |
| **Prestador / atendente** | "Ver o dia, bloquear férias, saber quem confirmou" | Consulta o dia (UI ou agente); bloqueia grade; vê o compromisso aparecer **na hora** no seu Google Calendar (RF-12) |
| **Dono** | "Menos buraco na agenda, menos falta" | Métricas de ocupação e no-show; cobra política de confirmação |
| **Agente de atendimento** | Fala com o cliente final: entende o pedido, checa grade, marca, lembra, remarca — **para uma pessoa por vez** | Canal inbound (§9.1); credencial de papel `atendimento` (RF-18) |
| **Agente administrativo** | Da equipe: opera a plataforma por conversa como alternativa ao painel — cria agendas, define grade, consulta apontamentos | `agenda-admin-mcp` (§14.5); credencial de papel `administrativo` (RF-18) |

**Jornada mestra:** cliente manda mensagem (§9.1) → agente entende a intenção e
a data (§8 IA-01/IA-04) → consulta slots (RF-02/03) → marca sem double-booking
(RF-04) → confirmação + lembretes via template (RF-05) → cliente confirma ou
remarca por resposta (RF-06) → tarefa espelho (RF-07), Google Calendar (RF-12)
e feed .ics (RF-11) refletem tudo.

**Jornada administrativa (RF-18, §14.5):** alguém da equipe pede ao seu agente
"abre a agenda da Dra. Marina, seg a sex das 9h às 17h" → o agente autentica no
`agenda-admin-mcp` com credencial de papel `administrativo` → cria o recurso e
a grade pelas mesmas rotas que a UI usa → a tela T-02 reflete na hora. É a
mesma API; muda quem tem autoridade para quê.

---

## 6. Escopo

### 6.1 Dentro
1. Cadastro de serviços (preço, duração, recursos)
2. Grade de disponibilidade (horário de trabalho, intervalos, bloqueios)
3. Agendamento por conversa (linguagem natural → slot)
4. **`canal-service`**: adapter de mensageria (Telegram + Evolution + Z-API;
   Meta como interface/aula), templates, inbound, opt-out — nasce aqui, serve
   M3 e M4
5. Confirmações e lembretes automáticos pelo canal
6. Reagendamento e cancelamento com devolução do slot
7. Espelho no Gestor de Tarefas
8. **Integração Google Calendar** (RF-12): push de eventos via API + busy-read
   no motor de slots, com OAuth por prestador
9. Feed .ics somente-leitura por recurso (RF-11) — opção sem OAuth
10. **Link público de auto-agendamento, opcional** (RF-13) — com configuração
    de caução prevista (cobrança no roadmap)
11. **Fila de espera** (RF-14) — cancelou, o próximo da fila recebe oferta pelo canal
12. **Recorrência simples** (RF-15) — série semanal/quinzenal
13. **Integração Calendly, opcional e one-way** (RF-16) — agendamentos feitos
    lá entram na agenda via webhook
14. **Documentação OpenAPI servida por Scalar** (RF-17) — o contrato público da API
15. **Papéis, escopos e credenciais de agente** (RF-18) — agente de atendimento
    e agente administrativo têm autoridades diferentes, e a diferença é
    verificada, não combinada
16. **Isolamento do agente de atendimento** (RF-19) — quem atende um cliente
    alcança os dados daquele cliente, e de mais ninguém
17. **`agenda-admin-mcp`** (§14.5) — a equipe operando a plataforma por
    conversa, como alternativa ao painel
15. **Telas web** (§12): UI do prestador (agenda, cadastros, integrações,
    canal, métricas) + páginas públicas — sempre como segundo cliente da API
16. Migração da agenda existente para a nuvem, com histórico preservado

### 6.2 Fora (ver roadmap em §18)
Sincronização bidirecional Google/Outlook (push + busy-read cobrem o módulo;
bidirecional é roadmap) · hold temporário de slot · cobrança efetiva de
sinal/caução (Pix — roadmap; a configuração já existe no link público) ·
pacotes de sessões (roadmap) · API oficial da Meta (roadmap) · videochamada ·
outras plataformas de booking além do Calendly.

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
- A conversa é a interface principal — sem formulário obrigatório. O link
  público (RF-13) é a via alternativa opcional, nunca a padrão.

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
Definidas nos conectores MCP (§14). São **dois catálogos**, porque são duas
autoridades (RF-18): 8 tools de atendimento no `agenda-mcp` (escopos
`agenda:read` / `agenda:write` / `agenda:cancel`) e 11 tools de operação no
`agenda-admin-mcp` (§14.5). Cancelamento atrás de confirmação humana nos dois.

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

### RF-11 — Feed .ics somente-leitura (opção sem OAuth)
**Critérios de aceite**
- URL por recurso com token: `GET /ics/{token}.ics` — assinável no Google
  Calendar e Apple Calendar.
- Token revogável e regenerável (vazou o link → revoga, gera outro).
- Eventos com timezone correto (`America/Sao_Paulo`), título com serviço +
  cliente (configurável: modo privado só mostra "ocupado").
- Compromisso cancelado sai do feed na próxima leitura.
- **Expectativa gerenciada em aula:** o Google atualiza calendários assinados
  em ciclos longos (horas, não controlamos). O feed é visão consolidada, não
  notificação em tempo real — tempo real no Google é papel do push (RF-12);
  lembrete em tempo real é papel do canal (RF-05).

### RF-12 — Integração Google Calendar (push + busy-read)

> A integração-base de calendário: a maioria dos alunos já vive no Google
> Calendar. O prestador conecta a conta uma vez e a agenda passa a refletir lá
> **na hora** — sem o ciclo de horas do .ics.

**Critérios de aceite**
- OAuth por prestador/recurso, com **escopo mínimo** (`calendar.events` +
  free/busy); tokens cifrados; desconectar revoga os tokens e apaga as credenciais.
- **Push:** compromisso criado, reagendado ou cancelado reflete no Google
  Calendar do prestador em < 60 s (evento criado/movido/removido via API).
- **Busy-read:** o motor de slots (`GET /slots`) consulta free/busy do Google e
  **não oferece** horário ocupado por evento externo (reunião marcada direto no
  Google bloqueia o slot).
- Falha na API do Google **não bloqueia** o agendamento — push entra na mesma
  fila de retry do espelho de tarefas (RF-07); busy-read usa cache curto e, com
  Google fora do ar, calcula só com dados locais registrando aviso.
- Bidirecional completa (editar/arrastar o evento no Google reflete na agenda)
  fica no roadmap (§18) — o evento pushado leva na descrição o aviso "gerencie
  pela agenda".
- Sem OAuth conectado, tudo funciona como antes: feed .ics (RF-11) é o fallback.

### RF-13 — Link público de auto-agendamento (opcional)

> A conversa continua sendo a tese do módulo. O link existe para o cliente que
> prefere clicar — e é onde a caução anti no-show vai morar (roadmap).

**Critérios de aceite**
- Link por serviço (e opcionalmente recurso), com slug próprio:
  `GET /agendar/{slug}` — página pública mínima que consome o **mesmo**
  `GET /slots` e o mesmo `POST /appointments` (mesmas regras, mesma constraint
  anti-double-booking; sem caminho privilegiado).
- Prestador ativa/desativa o link quando quiser; desativado, a URL responde
  com mensagem clara.
- Na criação do link, configuração **opcional** de caução/sinal — **desligada
  por padrão**; nesta fase o campo apenas informa o valor na página (a cobrança
  via Pix é roadmap §18).
- Agendamento pelo link entra com `origem: cliente`, dispara a mesma régua de
  confirmação/lembretes (RF-05) e exige nome + telefone (mínimo LGPD).
- Rate limit por IP na página pública; sem enumeração de agenda (só slots livres).

### RF-14 — Fila de espera

**Critérios de aceite**
- Horário desejado ocupado → agente (ou link público) oferece entrar na fila
  para uma janela desejada (ex.: "quinta à tarde").
- Cancelamento que libera slot compatível → job oferece ao **primeiro** da fila
  via template WhatsApp, com janela de aceitação configurável (padrão: 30 min).
- Sem resposta na janela → oferta expira e passa ao próximo; o slot permanece
  livre na grade durante a oferta (**sem hold** — quem confirmar primeiro leva;
  a mensagem de oferta diz isso).
- Aceite ("quero") agenda de forma atômica pela mesma constraint (RF-04); se o
  slot já foi tomado, o agente oferece as 3 alternativas mais próximas.
- Opt-out respeitado (RF-10): cliente fora do canal não recebe oferta — a
  entrada na fila avisa isso e cria tarefa para contato humano.
- Fila visível ao prestador (UI e `agenda://dia/{data}`), com posição e janela.

### RF-15 — Recorrência simples

**Critérios de aceite**
- Série semanal ou quinzenal com N ocorrências **ou** data-fim ("toda terça às
  10h até dezembro") — sem RRULE completo; a regra é deliberadamente simples.
- Cada ocorrência é um `appointment` próprio ligado à série (`series_id`) —
  lembretes, confirmação e no-show funcionam por ocorrência sem caso especial.
- Conflito em uma ocorrência na criação da série → a série é criada, a
  ocorrência conflitada fica pendente com 3 alternativas propostas — a série
  não quebra.
- Cancelar distingue **"esta ocorrência"** de **"todas as futuras"** (com
  confirmação humana quando disparado pelo agente, como em RF-06).
- Pacotes de sessões (10 sessões compradas, controle de saldo) ficam no
  roadmap (§18).

### RF-16 — Integração Calendly (opcional, one-way)

> Para o aluno que já opera no Calendly e está migrando: os agendamentos de lá
> aparecem aqui. Só o Calendly nesta etapa — outras plataformas, roadmap.

**Critérios de aceite**
- Webhook do Calendly (`invitee.created`, `invitee.canceled`) →
  `POST /webhooks/calendly` cria/cancela `appointment` com `origem: calendly`.
- Verificação de assinatura do webhook; idempotência por ID do evento (padrão
  de webhook do programa, §9).
- **One-way:** a agenda nunca escreve no Calendly; o compromisso importado é
  marcado como externo (reagendar/cancelar de verdade acontece lá; a agenda
  reflete pelo próximo webhook).
- Compromisso importado ocupa o slot na grade (constraint vale) e entra no
  espelho de tarefas e no Google Calendar como qualquer outro — mas **não**
  dispara a régua de lembretes por padrão (o Calendly já manda os dele;
  configurável).
- Integração **opcional**: sem configurar, nada muda.

### RF-17 — Documentação OpenAPI servida por Scalar

> API-first de verdade: a documentação é o contrato. É ela que a UI, o link
> público, os alunos e — via fachada — o `agenda-mcp` consomem. Aplicação
> **agent-friendly** nasce aqui: endpoints autenticados, erros com `hint`,
> descrições que servem de texto para as tools.

**Critérios de aceite**
- OpenAPI 3.1 gerada pelo FastAPI, servida por **Scalar** em `/docs`
  (substituindo o Swagger UI padrão).
- Toda rota com descrição **prescritiva** (quando chamar, não só o que faz),
  exemplos de request/response e erros documentados no formato
  `{code, message, hint}` — o mesmo texto alimenta as descrições das tools MCP
  (§14): uma fonte, dois consumidores.
- Rotas com autenticação e **escopo explícito na spec** — os sete de RF-18; o
  escopo declarado é o mesmo cobrado em execução, e é a fonte dos escopos das
  tools MCP. Rotas públicas (link, .ics, webhooks) marcadas como tal.
- A spec exportada (`/openapi.json`) é artefato versionado do módulo — mudança
  de contrato aparece no diff.
- Critério de aula: aluno lê o `/docs` e executa um agendamento completo só
  pela documentação, sem abrir o código.

### RF-18 — Papéis, escopos e credenciais de agente

> **O requisito que separa duas coisas que estavam juntas.** Um agente de
> WhatsApp/Telegram atende o **cliente final**; um agente da equipe **opera a
> plataforma**. São autoridades diferentes, e tratá-las como uma só foi o
> erro que este requisito corrige: até aqui toda credencial autenticada tinha
> poder total sobre a organização — o bot do canal podia criar serviços,
> apagar grade e ler o cadastro de todos os clientes.

**Vocabulário de autoridade (7 escopos)**

| Escopo | Cobre |
|---|---|
| `agenda:read` | catálogo, slots, grade semanal, o **próprio** compromisso |
| `agenda:write` | agendar, reagendar, confirmar, fila — para **um** cliente |
| `agenda:cancel` | cancelar um compromisso |
| `agenda:operacao` | a operação inteira: dia completo, todos os compromissos, fila completa, histórico, bloqueios, no-show, série |
| `agenda:admin` | escrita de catálogo e grade — serviços, recursos, janelas, bloqueios |
| `canal:admin` | driver, credenciais de mensageria, `webhook_url`, templates, opt-outs |
| `credenciais:admin` | emitir e revogar credenciais |

**Papéis são presets, não gaiolas.** O papel preenche os escopos no momento da
criação; a autoridade real é a lista gravada na credencial, que o
administrador ajusta uma a uma.

| Papel | Escopos padrão |
|---|---|
| `atendimento` | `read`, `write` |
| `operacao` | `atendimento` + `operacao`, `cancel` |
| `administrativo` | `operacao` + `agenda:admin`, `canal:admin` |

**Critérios de aceite**
- Credencial de papel `atendimento` recebe **403** em toda rota de catálogo,
  grade, canal e visão da operação — e a mensagem de erro diz o que ela tem e
  o que a operação exige.
- Credencial com `agenda:read` + `agenda:write` **não** cancela (é o mesmo
  aceite do §14.4, agora executável).
- Credenciais vivem em tabela (§10), com **revogação sem redeploy**. O token
  em claro existe uma única vez, na criação; o banco guarda só o hash.
- **`credenciais:admin` nunca entra em preset de credencial de agente.** Só
  humano autenticado por JWT emite credencial — um token administrativo
  comprometido não pode emitir outro para sobreviver à própria revogação.
- A **primeira** credencial de uma organização nasce por linha de comando no
  servidor, nunca por rota: um endpoint que emite credencial administrativa é
  um backdoor permanente.
- `GET /credenciais/eu` devolve organização, papel, escopos e titular a
  qualquer credencial autenticada — descobrir a própria autoridade não é
  privilégio, e é o que permite ao agente falhar rápido em vez de tentar o que
  seria recusado.
- Toda ação de agente é registrada em `agent_audit_log` (§10, `00` §5.8),
  incluindo **em nome de qual cliente** ela foi feita.

### RF-19 — Isolamento do agente de atendimento

> Escopo separa *capacidades*; isto separa *dados*. Sem ele, um agente de
> atendimento com escopo mínimo ainda alcançaria o compromisso de qualquer
> pessoa da organização — bastava conhecer o id.

**Critérios de aceite**
- A credencial de atendimento carrega o **titular**: o endereço do cliente que
  ela está atendendo (E.164 no WhatsApp, `tg:<chat_id>` no Telegram).
- O titular é **cunhado onde o endereço é provado** — no `canal-service`,
  depois da verificação do segredo do webhook — e viaja como token de sessão
  com validade curta. O agente não declara para quem trabalha; ele recebe essa
  informação já assinada. Um header auto-declarado seria o ator restringido
  definindo a própria restrição.
- Compromisso de outro titular responde **404**, não 403: 403 confirmaria que
  aquele compromisso existe.
- `POST /appointments` e `POST /waitlist` gravam o titular da credencial —
  ignorando divergência no corpo.
- `GET /waitlist` devolve **apenas** as entradas do titular; a filtragem é do
  servidor, nunca do cliente.
- Sem `agenda:operacao`, a saída **omite** `risco_no_show`, `risco_detalhe` e
  `observacoes`: são dados *sobre* o cliente que ele não deve ouvir do bot.
- O titular faz parte da chave de idempotência — senão repetir a
  `Idempotency-Key` de outra pessoa devolveria o corpo dela, porque a
  verificação de idempotência precede as guardas de propriedade.
- Endereços são normalizados na escrita e na comparação: `+5511998765432` e
  `+55 11 99876-5432` são o mesmo cliente, e tratá-los como diferentes
  deixaria a pessoa sem acesso ao próprio horário.

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
| **Técnica** | O agente classifica a intenção (confirmar / cancelar / remarcar / aceitar oferta da fila de espera / dúvida / opt-out / fora de contexto) e age via tools MCP |
| **Salvaguarda** | Cancelamento e remarcação seguem exigindo os fluxos com confirmação (RF-06) — a classificação de intenção **não** pula as regras |
| **Fallback** | Intenção não reconhecida com confiança → agente responde pedindo esclarecimento; na segunda falha, encaminha ao humano (tarefa + a conversa fica marcada "aguardando humano") |
| **Opt-out** | "SAIR" e variações são detectadas **antes** do LLM, por regra determinística no canal (RF-10) — sair do spam não pode depender de IA acertar |

---

## 9. Integrações externas (API autenticada)

> Padrão de webhook do programa (M1 §9): responder 2xx rápido, processar
> assíncrono, idempotência por ID de evento, segredo verificado, replay tolerado.
> Segredos por organização cifrados, write-only, nunca em log.

### 9.1 Mensageria via `canal-service` — 4 drivers

| | Telegram | Evolution API | Z-API | Meta Cloud API |
|---|---|---|---|---|
| **Status no programa** | ✅ implementado | ✅ implementado | ✅ implementado | interface + aula (extensão guiada) |
| **Auth** | token de bot (BotFather) | apikey da instância self-host | client-token da instância | token de app + verificação de negócio |
| **Custo** | zero | zero (roda no próprio VPS) | assinatura por instância | por conversa/template (tabela Meta) |
| **Preparo** | ~1 min, sem chip nem QR | chip dedicado + pareamento por QR | assinatura + instância | verificação de negócio |
| **Mensagem ativa** | texto livre (template renderizado) | texto livre (template renderizado) | texto livre (template renderizado) | **template pré-aprovado obrigatório** |
| **Risco** | nenhum (bot é identidade própria) | não-oficial — banimento possível | não-oficial — banimento possível | oficial, sem risco de ToS |
| **Endereço do cliente** | `tg:<chat_id>` | E.164 | E.164 | E.164 |
| **Webhook inbound** | → `/webhooks/canal/telegram` | por instância → `/webhooks/canal/evolution` | → `/webhooks/canal/zapi` | → `/webhooks/canal/meta` |

**Telegram é o canal de demonstração**: o token sai do BotFather em um minuto,
qualquer pessoa da turma testa no próprio celular e não há chip, QR nem risco
de bloqueio no caminho. Ele existe porque prova a promessa do adapter — a
**mesma suíte de aceite passa nos três drivers implementados**, inclusive num
canal que sequer usa telefone. É a evidência mais forte de que trocar de
canal é configuração.

Aula prática: Telegram para todo mundo mexer, Evolution self-host no VPS
(WhatsApp de verdade, QR code ao vivo) e Z-API como segunda instância para
**demonstrar a troca de driver por configuração**. Meta entra como aula:
verificação, templates, tabela de preços — e por que o sistema já está pronto
para ela (template-first).

> **Onde a abstração vaza, e como fica contida:** o sistema nasceu com
> `telefone` como endereço do cliente. Telegram não usa telefone, usa
> `chat_id`. Em vez de renomear tudo (refactor grande) ou guardar o número cru
> (ambíguo), o canal grava `tg:<chat_id>` — autodescritivo e impossível de
> colidir com E.164, que sempre começa com `+`. O campo passa a significar
> "endereço do cliente **neste canal**". Reconhecer o vazamento e contê-lo com
> uma convenção legível é o conteúdo da aula.

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

### 9.5 Google Calendar API (RF-12)
- **OAuth 2.0 por prestador**, escopo mínimo: `calendar.events` (push) +
  free/busy (busy-read). Tokens cifrados, write-only na API, revogados ao
  desconectar.
- **Push:** criação/movimentação/remoção de evento via API — sem webhook do
  Google nesta fase (bidirecional é roadmap §18, que aí sim exige webhooks +
  sync tokens).
- **Busy-read:** consulta free/busy com cache curto (ex.: 60 s) no motor de
  slots; indisponibilidade do Google degrada para cálculo local com aviso.
- **Quotas e verificação (conteúdo de aula):** app OAuth em modo de teste exibe
  tela "não verificado" e exige cadastrar usuários de teste — suficiente para o
  programa; a verificação do app no Google é lição de casa documentada.

### 9.6 Calendly (RF-16 — opcional, one-way)
- Webhook `invitee.created` / `invitee.canceled` → `/webhooks/calendly`, com
  verificação de assinatura e idempotência por ID de evento (padrão §9).
- A agenda **não escreve** no Calendly; importado é marcado `origem: calendly`.
- Única plataforma de booking externa desta etapa — decisão de simplicidade;
  outras ficam no roadmap (§18).

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
  origem text default 'agente',       -- agente|cliente|humano|calendly
  observacoes text,
  task_id uuid,                       -- espelho no Gestor de Tarefas
  series_id uuid,                     -- RF-15: recorrência (references recurrence_series)
  google_event_id text,               -- RF-12: push no Google Calendar
  external_ref text,                  -- RF-16: id do evento no Calendly (idempotência)
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

create table google_calendar_links (  -- RF-12: OAuth por prestador/recurso
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  resource_id uuid not null references resources(id),
  calendar_id text not null,          -- calendário de destino no Google
  credenciais jsonb not null,         -- tokens OAuth cifrados; write-only na API
  ativo boolean default true,
  revogado_em timestamptz,
  created_at timestamptz default now(),
  unique (org_id, resource_id)
);

create table booking_links (          -- RF-13: link público opcional
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  service_id uuid not null references services(id),
  resource_id uuid references resources(id),   -- opcional: link por profissional
  slug text not null unique,
  exige_caucao boolean default false, -- cobrança efetiva (Pix) no roadmap §18
  valor_caucao numeric(14,2),
  ativo boolean default true,
  created_at timestamptz default now()
);

create table waitlist (               -- RF-14: fila de espera
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  service_id uuid not null references services(id),
  resource_id uuid references resources(id),
  cliente_nome text not null,
  cliente_telefone text not null,
  janela_desejada tstzrange not null, -- ex.: quinta 12h–18h
  status text not null default 'aguardando', -- aguardando|ofertado|aceito|expirado|cancelado
  ofertado_em timestamptz,
  expira_em timestamptz,              -- janela de aceitação da oferta
  created_at timestamptz default now()
);

create table recurrence_series (      -- RF-15: recorrência simples
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  service_id uuid not null references services(id),
  resource_id uuid not null references resources(id),
  frequencia text not null check (frequencia in ('semanal','quinzenal')),
  dia_semana int not null check (dia_semana between 0 and 6),
  hora_inicio time not null,
  fim_em date,                        -- data-fim OU
  ocorrencias int,                    -- número de ocorrências
  ativo boolean default true,
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

```sql
-- RF-18: a autoridade de cada integração, revogável sem redeploy.
-- O token em claro nunca é gravado — só o hash. `escopos` é a autoridade real;
-- `papel` é apenas o preset que a preencheu.
create table agent_credentials (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null,
  nome          text not null,        -- "Agente do WhatsApp", "Copiloto da recepção"
  papel         text not null check (papel in ('atendimento','operacao','administrativo')),
  escopos       text[] not null,
  token_hash    text not null unique, -- sha256; entropia alta dispensa bcrypt
  prefixo       text not null,        -- só para a UI identificar a linha
  ativo         boolean not null default true,
  criada_em     timestamptz default now(),
  ultimo_uso_em timestamptz,
  revogada_em   timestamptz
);

-- `00` §5.8 — a pergunta que esta tabela existe para responder:
-- "quem cancelou esse horário, o agente ou uma pessoa — e em nome de quem?"
create table agent_audit_log (
  id             bigserial primary key,
  org_id         uuid not null,
  mcp_server     text not null,       -- agenda | agenda-admin
  tool_name      text not null,       -- nome da tool, ou "METODO /rota"
  client_id      uuid,                -- agent_credentials.id
  actor          text,
  titular        text,                -- em nome de qual cliente (RF-19)
  args_hash      text,                -- hash dos argumentos, nunca o valor cru
  resultado      text not null check (resultado in ('ok','erro','recusado')),
  error_code     text,
  latencia_ms    int,
  confirmado_por uuid,
  created_at     timestamptz default now()
);
```

> **`idempotency_keys` ganha `titular` na chave primária** (RF-19). A
> verificação de idempotência roda antes das guardas de propriedade nos
> handlers: sem o titular, repetir a `Idempotency-Key` de outra pessoa
> devolveria o corpo dela sem passar por checagem nenhuma.

**Índices:** `appointments(org_id, resource_id)` · `appointments using gist (periodo)` ·
`appointments(org_id, cliente_telefone)` · `appointments(series_id)` ·
`reminders(agendado_para) where enviado_em is null` ·
`waitlist(org_id, status) where status in ('aguardando','ofertado')` ·
`channel_messages(org_id, telefone, created_at desc)` ·
`appointments(external_ref) where external_ref is not null` (idempotência Calendly) ·
`agent_credentials(token_hash) where ativo and revogada_em is null` (o caminho quente
da autenticação) · `agent_audit_log(org_id, created_at desc)`.

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

GET  /integracoes/google/conectar     # RF-12: início do OAuth (redirect)
GET  /integracoes/google/callback     DELETE /integracoes/google/{resource_id}
GET  /booking-links                   POST /booking-links      # RF-13
GET  /agendar/{slug}                  # página pública do link (rate limit por IP)
GET  /waitlist?service_id=&status=    # RF-14: fila (tela T-06)
POST /waitlist                        # entrar na fila
POST /waitlist/{id}/aceitar           POST /waitlist/{id}/cancelar
POST /appointments/recorrentes        # RF-15: cria série + ocorrências
POST /webhooks/calendly               # RF-16 (assinatura verificada)
GET  /credenciais/eu                  # RF-18: papel, escopos e titular desta credencial
GET  /credenciais                     DELETE /credenciais/{id}   # revogar (credenciais:admin)
GET  /docs                            # RF-17: OpenAPI 3.1 servida por Scalar
GET  /openapi.json                    # spec exportada (artefato versionado)

# canal-service (contrato em 00 §4.8)
POST /canal/enviar                    # sessao|template — template-first
GET  /canal/templates                 POST /canal/templates
GET  /canal/mensagens?telefone=
POST /canal/webhook-url/revelar       # o segredo do webhook sai redigido nas leituras
POST /webhooks/canal/telegram         POST /webhooks/canal/evolution
POST /webhooks/canal/zapi             POST /webhooks/canal/meta
```

Autorização por escopo em toda rota (RF-18) — o escopo exigido é declarado na
própria spec e é a fonte dos escopos das tools MCP. Emitir credencial **não é
rota**: nasce por linha de comando (`make credencial`). O `canal-service` só
aceita chamadas dos serviços do programa (credencial service-to-service) —
nunca do navegador; a única exceção pública é `/webhooks/canal/*`, que drivers
de nuvem precisam alcançar e o segredo protege.

---

## 12. Telas (UI web — Vite + React)

> **Princípio (e conteúdo de aula):** a UI é o **segundo cliente** da API —
> nasce depois do endpoint, consome as mesmas rotas documentadas no `/docs`
> (RF-17) e não tem caminho privilegiado: toda ação da tela existe antes como
> rota autenticada. A operação do dia a dia acontece por conversa; a UI serve
> para **configurar** (setup) e **supervisionar** (ver, conferir, auditar).
> SPA em Vite + React (stack canônica, `00` §3.2), autenticada via Supabase
> Auth — exceto as duas páginas públicas marcadas abaixo.

### 12.1 Telas do prestador (autenticadas)

| # | Tela | Para quê | Rotas principais que consome |
|---|---|---|---|
| T-01 | **Login / organização** | Entrar; trocar de organização quando houver mais de uma | Supabase Auth |
| T-02 | **Agenda do dia/semana** (tela principal) | Ver o dia por recurso: compromissos com status por cor (agendado, confirmado, cancelado, realizado, no-show), risco de no-show visível, buracos evidentes | `GET /agenda/day` · `GET /appointments` |
| T-03 | **Detalhe do compromisso** | Ficha completa + histórico de alterações (quem, quando, por quê); ações: confirmar, reagendar, cancelar, marcar no-show | `POST /appointments/{id}/…` |
| T-04 | **Serviços** | Cadastrar/editar serviço: nome, duração, preço, buffers, recursos exigidos | `GET/POST /services` |
| T-05 | **Grade e bloqueios** | Horário de trabalho semanal por recurso; bloqueios pontuais (férias, feriado, almoço) com motivo | `POST /availability/rules` · `POST /availability/blocks` |
| T-06 | **Fila de espera** | Ver a fila por serviço/janela: posição, status (aguardando, ofertado, expirado), quem recebeu oferta | `GET /waitlist` (listagem) |
| T-07 | **Links públicos** | Criar/ativar/desativar links de auto-agendamento; configurar caução (RF-13) | `GET/POST /booking-links` |
| T-08 | **Integrações** | Conectar/desconectar Google Calendar (botão OAuth + status), gerar/revogar tokens .ics, configurar webhook Calendly | `/integracoes/google/…` · `/ics/tokens` |
| T-09 | **Canal de conversa** | Configurar driver (Telegram/Evolution/Z-API/Meta), número dedicado ou bot, **QR code da Evolution ao vivo**, status da conexão; editar templates (versionados) e ver opt-outs | `canal-service` (via backend; nunca direto do navegador) |
| T-11 | **Credenciais de agente** (RF-18) | Emitir credencial escolhendo o papel e ajustando escopos um a um; revogar; ver último uso. O token aparece **uma única vez** | `GET/DELETE /credenciais` |
| T-10 | **Métricas** | Os números do §4: ocupação, no-show antes/depois do lembrete, entrega de mensagens, agendamentos por origem (conversa, link, Calendly) | agregações de `GET /appointments` + canal |

### 12.2 Páginas públicas (sem login)

| # | Página | Para quê | Observações |
|---|---|---|---|
| P-01 | **`/agendar/{slug}`** (RF-13) | Cliente escolhe serviço → vê slots livres → informa nome + telefone → agenda | Mesmo motor `GET /slots`; rate limit por IP; coleta mínima (LGPD §13); mostra valor da caução quando configurada |
| P-02 | **`/ics/{token}.ics`** (RF-11) | Feed de calendário assinável | Não é tela navegável — URL para o app de calendário |

### 12.3 Critérios de aceite

- Nenhuma tela chama o banco ou lógica própria de negócio: **toda ação passa
  pela API pública documentada** — deletar a UI inteira não remove nenhuma
  capacidade do sistema (teste de aula: tudo que a tela faz, o agente faz).
- T-02 reflete mudanças feitas por conversa **sem exigir refresh manual**
  (polling simples basta; websocket não é requisito).
- Ações destrutivas na UI (cancelar, desativar link, revogar token) pedem
  confirmação — o mesmo gradiente de risco do agente vale para o humano.
- T-09 nunca exibe credenciais gravadas (write-only, `00` §4.8) e mostra a
  `webhook_url` **redigida** — o segredo nela autentica o inbound, e quem o
  obtém forja mensagem como qualquer cliente.
- T-11 mostra o token apenas na criação; depois, só o prefixo. Revogar tem
  efeito em segundos, sem redeploy.
- Responsivo o suficiente para o prestador consultar T-02 no celular; a UI de
  cadastro (T-04, T-05) pode assumir desktop.
- A página pública P-01 funciona sem JavaScript pesado e carrega em < 2 s em 4G
  — é a vitrine do prestador.

---

## 13. Requisitos não funcionais

- **Consistência:** `EXCLUDE USING gist` é inegociável — a regra vive no banco.
- **Timezone:** cálculo de slot sempre em America/Sao_Paulo, persistência em UTC
  (`tstzrange`); suíte de testes de borda de horário de verão (o Brasil não tem
  DST hoje, mas a regra pode voltar — o teste fica).
- **Job de lembretes:** roda a cada 5 min no VPS; janela de tolerância de 15 min;
  idempotente (o `unique` em `reminders` impede reenvio).
- **Latência:** `GET /slots` para 30 dias em < 400 ms (p95).
- **Resiliência:** driver de canal fora do ar não perde lembrete — fila com
  retry; esgotado, tarefa manual. Trocar de driver não perde mensagens em fila.
  Push ao Google Calendar na mesma fila de retry do espelho de tarefas;
  busy-read com cache curto e fallback local (Google fora do ar nunca derruba
  o motor de slots).
- **LGPD (telefone e histórico de conversa do cliente final):**
  - Telefone é dado pessoal: coleta mínima, finalidade declarada (agendamento e
    lembretes), sem uso para marketing sem consentimento separado.
  - **Opt-out é imediato e determinístico** (RF-10) — não depende de IA.
  - Pedido de eliminação: anonimização efetiva (nome/telefone sobrescritos no
    histórico; compromissos futuros cancelados com aviso ao humano).
  - Conversas retidas 12 meses (configurável); credenciais de driver cifradas.
  - Tokens OAuth do Google: escopo mínimo, cifrados, write-only na API,
    eliminados ao desconectar (RF-12).
  - Página pública do link (RF-13): coleta mínima (nome + telefone), finalidade
    declarada na própria página.
- **Segurança:** RLS por `org_id` em todas as tabelas (canal incluído);
  rate limit por credencial; webhook com segredo por driver (Calendly incluído);
  rate limit por IP nas rotas públicas (`/agendar/{slug}`, `/ics/{token}.ics`).
  - **Autoridade por credencial, não por autenticação** (RF-18): autenticar não
    concede tudo. Escopo é verificado em toda rota, e o escopo declarado na
    spec é o mesmo cobrado em execução.
  - **Falhar fechado:** o modo de desenvolvimento aceita identificação simples
    da organização por header; por isso o padrão da configuração é
    **produção** — um deploy que esqueça a variável não pode virar porta
    aberta.
  - **Segredo de webhook é chave da porta, não configuração**: sai redigido em
    toda leitura, porque quem o obtém forja mensagem de entrada como qualquer
    cliente da organização. Revelá-lo é ato explícito.
  - **Toda ação de agente é auditada** (`agent_audit_log`), com o cliente em
    nome de quem foi feita.

---

## 14. Conectores MCP

> Requisitos transversais em `00-ARQUITETURA-BASE.md` §5. Repete o padrão
> estabelecido pelo `crm-mcp` no módulo 1.

São **dois** servidores, porque são duas autoridades (RF-18):

| Servidor | Quem usa | Superfície |
|---|---|---|
| **`agenda-mcp`** (§14.1–14.4) | agente que atende o **cliente final** | 8 tools de atendimento |
| **`agenda-admin-mcp`** (§14.5) | agente **da equipe** | 11 tools de operação e configuração |

> **Por que dois e não um.** É a mesma razão de `00` §5.2 ("um servidor por
> domínio permite conceder acesso parcial"), aplicada um nível abaixo. Com um
> servidor só, a separação dependeria de o servidor lembrar de checar escopo
> em cada tool; com dois, as tools administrativas **não existem** no endpoint
> que o lado de atendimento alcança. E mantém cada catálogo pequeno o bastante
> para o modelo escolher bem — 19 tools num servidor degradariam a escolha.

#### `agenda-mcp` — o atendimento (§14.1 a §14.4)

**Endpoint:** `https://mcp.SEU-DOMINIO.com/agenda/mcp` · Streamable HTTP
**Escopos:** `agenda:read` · `agenda:write` · `agenda:cancel`
**Fase de auth:** já nasce em fase 2 (OAuth 2.1) — o padrão veio pronto do M1

> **Este é o conector mais exposto do programa.** É ele que o cliente final
> aciona, indiretamente, ao mandar mensagem. Escopo apertado e confirmação de
> cancelamento não são detalhes.
>
> **Relação com a API:** o conector é fachada fina sobre a API documentada em
> OpenAPI/Scalar (RF-17) — as descrições das tools reutilizam o texto da spec;
> nenhuma regra de negócio vive aqui. A trilha do módulo é API → documentação →
> MCP: a aplicação nasce agent-friendly pelo contrato, não pelo conector.

### 14.1 Tools

| Tool | Escopo | `readOnly` | `destructive` | `idempotent` | Confirmação |
|---|---|:---:|:---:|:---:|---|
| `agenda_listar_servicos` | `agenda:read` | ✅ | — | ✅ | — |
| `agenda_consultar_slots` | `agenda:read` | ✅ | — | ✅ | — |
| `agenda_meu_dia` | `agenda:read` | ✅ | — | ✅ | — |
| `agenda_agendar` | `agenda:write` | — | — | ✅ | — |
| `agenda_reagendar` | `agenda:write` | — | — | ✅ | — |
| `agenda_confirmar` | `agenda:write` | — | — | ✅ | — |
| `agenda_fila_espera` | `agenda:write` | — | — | ✅ | — |
| `agenda_cancelar` | `agenda:cancel` | — | ✅ | ✅ | **sim** |

`agenda_fila_espera` (RF-14) coloca o cliente na fila para uma janela desejada
quando `agenda_consultar_slots` não devolve horário aceitável — a descrição da
tool instrui o agente a oferecê-la em vez de encerrar com "não tem horário".
`agenda_consultar_slots` já considera o busy do Google Calendar (RF-12) — o
agente não precisa saber que a integração existe. O catálogo fica em 8 tools
(teto de 15 do programa preservado).

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

### 14.2 Resources

| URI | Conteúdo |
|---|---|
| `agenda://servicos` | Serviços ativos com preço, duração e buffers |
| `agenda://recursos` | Profissionais, salas e equipamentos ativos |
| `agenda://dia/{data}` | Agenda completa do dia, em linguagem clara |
| `agenda://compromisso/{id}` | Ficha do compromisso + histórico de alterações |
| `agenda://grade/{recurso_id}` | Horário de trabalho e bloqueios vigentes |

### 14.3 Prompts

| Prompt | O que faz |
|---|---|
| `agenda_do_dia` | Lê a agenda de hoje, destaca conflitos, faltas prováveis e buracos |
| `remarcar_semana` | Dado um bloqueio novo (férias, imprevisto), lista os afetados e propõe realocação |
| `confirmar_pendentes` | Lista compromissos das próximas 24h sem confirmação e prepara as mensagens |

### 14.4 Aceite do conector
- [ ] Servidor inspecionável no MCP Inspector com schemas e annotations corretos
- [ ] `agenda_cancelar` marcada com `destructiveHint: true` e bloqueada sem
      confirmação humana
- [ ] Credencial com `agenda:read` + `agenda:write` **não** consegue cancelar
- [ ] 10 chamadas simultâneas de `agenda_agendar` no mesmo slot → 1 sucesso,
      9 erros legíveis com alternativas
- [ ] Teste de borda de horário de verão não produz slot fantasma nem buraco
- [ ] Marcar, reagendar e confirmar por conversa, de outro dispositivo, com o
      notebook do aluno desligado

### 14.5 `agenda-admin-mcp` — a equipe operando por conversa

**Endpoint:** `https://mcp.SEU-DOMINIO.com/agenda/admin/mcp` · Streamable HTTP
**Escopos:** `agenda:read` · `agenda:operacao` · `agenda:admin` · `agenda:cancel` · `credenciais:admin`
**Auth:** bearer token de `agent_credentials` (RF-18), com escopos por credencial. OAuth 2.1 no roadmap (§18).

> É a alternativa ao painel: o que a equipe faz na UI, faz aqui por conversa.
> Criar a agenda de um profissional novo, abrir a grade da semana, bloquear
> férias, olhar o dia, ver quem está na fila.

**Regra inegociável:** o `agenda-admin-mcp` **não tem credencial própria**. Ele
repassa o bearer de quem o chamou e nunca decide autorização — quem decide é a
API. Dar-lhe uma credencial de serviço "para simplificar" recriaria exatamente
o *confused deputy* que o RF-18 eliminou.

| Tool | Escopo | O que faz |
|---|---|---|
| `agenda_admin_catalogo` | `agenda:read` | serviços **e** recursos numa chamada |
| `agenda_admin_servico_salvar` | `agenda:admin` | cria ou altera (id opcional) |
| `agenda_admin_recurso_salvar` | `agenda:admin` | cria ou altera uma **agenda** |
| `agenda_admin_grade_ver` | `agenda:operacao` | janelas e bloqueios do recurso |
| `agenda_admin_grade_definir` | `agenda:admin` | **declarativa**: substitui a semana inteira |
| `agenda_admin_bloqueio_criar` | `agenda:admin` | férias, feriado, imprevisto |
| `agenda_admin_bloqueio_remover` | `agenda:admin` | |
| `agenda_admin_dia` | `agenda:operacao` | os apontamentos de um dia, narrados |
| `agenda_admin_fila` | `agenda:operacao` | quem espera, posição e ofertas |
| `agenda_admin_cancelar` | `agenda:cancel` | elicitation antes de executar |
| `agenda_admin_credenciais_listar` | `credenciais:admin` | **só leitura** — emitir nunca é tool |

> **Por que `grade_definir` é declarativa.** A alternativa (listar → remover uma
> → criar duas) é justamente a sequência em que o modelo erra: esquece um
> passo e deixa a grade num estado que ninguém pediu. Substituir a semana
> inteira numa chamada atômica elimina três tools *e* um modo de falha.

**Critérios de aceite**
- Credencial de papel `atendimento` conectada a este servidor **não executa
  tool nenhuma de escrita** — e a recusa explica qual escopo falta.
- Token de outra organização não vê dado algum (RLS é a última linha).
- Emitir credencial **não é tool**: `agenda_admin_credenciais_listar` só lê.
- `agenda_admin_cancelar` usa elicitation; onde o cliente não suportar, cai no
  `confirmation_token` que a API já emite.
- Toda tool call vira uma linha em `agent_audit_log`.
- Aceite de aula: criar uma agenda nova (recurso + grade da semana) e conferir
  o resultado na tela T-02, **inteiramente por conversa**.

---

## 15. Demo final do módulo (critério de conclusão)

> **Marcar, reagendar e confirmar um horário inteiramente por conversa — no
> WhatsApp de verdade.**

**Roteiro executável ao vivo:**
1. Cliente manda **WhatsApp real** ("Quero marcar um corte quinta de tarde") →
   webhook inbound chega no VPS → agente consulta a grade e **oferece 3
   horários** com data por extenso.
2. Cliente escolhe → compromisso criado + confirmação por **template** enviada +
   tarefa espelho no Gestor de Tarefas + o horário aparece **na hora no Google
   Calendar do aluno** (push RF-12 — a turma vê o evento surgir).
3. "Preciso mudar para sexta" → reagendamento atômico: quinta volta para a grade
   na hora (demonstrado consultando `/slots` na frente da turma) — e um segundo
   "cliente" que estava na **fila de espera** recebe no WhatsApp a oferta do
   horário liberado (RF-14).
4. Lembrete de 24h dispara pelo job do VPS — **com o notebook do aluno
   desligado** — e chega no celular do "cliente".
5. Cliente responde "confirmo" → IA-04 classifica → status atualizado.
6. **Troca de driver ao vivo:** configuração muda de Evolution para Z-API e o
   mesmo fluxo roda — zero mudança de código.

Se qualquer passo exigir abrir um sistema manualmente, o módulo não está concluído.

---

## 16. Riscos

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
| Aluno espera .ics em tempo real | Alta | Baixo | Expectativa dita em aula: feed é visão; tempo real é o push (RF-12) |
| App OAuth do Google "não verificado" assusta o aluno | Alta | Baixo | Modo de teste com usuários cadastrados basta para o programa; verificação é lição de casa documentada |
| API do Google indisponível ou com quota estourada | Baixa | Médio | Push em fila de retry; busy-read com cache + fallback local — motor de slots nunca depende do Google |
| Oferta da fila expira e slot fica ocioso | Média | Baixo | Janela curta configurável (padrão 30 min) + repasse automático ao próximo; sem hold de slot |
| Aluno edita evento no Google e espera refletir na agenda | Média | Médio | Expectativa em aula: push é one-way; evento pushado avisa "gerencie pela agenda"; bidirecional no roadmap |

## 17. Plano de entrega

| Etapa | Entrega |
|---|---|
| 1 | Schema + migração da agenda para Supabase (reconciliada) |
| 2 | Serviços, recursos e grade de disponibilidade |
| 3 | Motor de slots (`GET /slots`) + constraint anti-double-booking |
| 4 | Agendamento, reagendamento atômico, cancelamento + **recorrência simples** (RF-15) |
| 5 | **OpenAPI + Scalar** (RF-17): contrato revisado, com exemplos, publicado em `/docs` — antes das integrações, porque é o contrato que elas consomem |
| 6 | **`canal-service`**: drivers Telegram + Evolution + Z-API, templates, inbound, opt-out |
| 7 | Job de lembretes via canal + espelho no Gestor de Tarefas + **fila de espera** (RF-14) |
| 8 | **Google Calendar: push + busy-read** (RF-12) + feed .ics (RF-11) + **link público** (RF-13) + webhook Calendly (RF-16) |
| 9 | **Papéis, escopos e credenciais** (RF-18) + **isolamento do atendimento** (RF-19) + **`agenda-admin-mcp`** (§14.5) — a equipe operando por conversa |
| 10 | **Conector MCP `agenda-mcp`** de atendimento (§14.1–14.4) + linguagem natural de datas + **demo final** |

As **telas (§12) nascem junto com a etapa da sua rota, nunca antes** — é o
API-first na prática: T-04/T-05 na etapa 2, T-02/T-03 na etapa 4, T-09 na 6,
T-06 na 7, T-07/T-08 e a página pública P-01 na 8, T-11 na 9, T-10 fecha com
a demo.

## 18. Roadmap (pós-programa)

Extensões registradas, em ordem aproximada de valor para o autônomo:

| Item | O que destrava | Por que não agora |
|---|---|---|
| **Sinal/caução via Pix no link público** | A medida mais eficaz contra no-show (reduções de 60–80% relatadas pelo mercado); a configuração já existe em `booking_links` (RF-13) | Cobrança com liquidação real está fora do programa (`00` §4.7) |
| **API oficial da Meta (WhatsApp Cloud API)** | Canal sem risco de banimento; templates já nascem `aprovado_meta`-ready (RF-10) | Verificação de negócio + custo por conversa; interface e aula já preparam a troca |
| **Pacotes de sessões** | "10 sessões de fisioterapia" com saldo — comum em serviços recorrentes | Recorrência simples (RF-15) cobre o essencial; pacote adiciona controle financeiro que conversa com o M4 |
| **OAuth 2.1 nos conectores MCP** | Substitui o bearer de `agent_credentials` por OAuth completo (`00` §5.4): PKCE, Protected Resource Metadata, resource indicators | O modelo de papéis e escopos (RF-18) já está no lugar; trocar o mecanismo de emissão do token não muda quem pode o quê. Entregar autoridade antes de cerimônia foi a escolha deliberada |
| **Rate limit por credencial** | 60 req/min e teto de escritas/hora por credencial (`00` §5.9) | Sem ele, credencial de atendimento vazada enumera clientes um a um. A tabela de credenciais já dá a base |
| **Sincronização bidirecional Google** | Editar no Google reflete na agenda | Webhooks + sync tokens + resolução de conflito consumiriam o módulo; push + busy-read entregam o valor central |
| **Hold temporário de slot** | Reserva durante a escolha | Estado que expira; a fila de espera e as alternativas cobrem o caso |
| **Outras plataformas de booking** | Importar de além do Calendly | Uma integração externa basta para ensinar o padrão |
