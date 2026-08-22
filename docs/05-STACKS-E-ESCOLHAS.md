> **Cópia congelada** (v1 · 2026-08-22) do contrato comum. Fonte da verdade: [Better-Knowledge/cpdf-comum](https://github.com/Better-Knowledge/cpdf-comum) — mudanças de contrato acontecem lá primeiro.

# Duas stacks, um programa
### Por que os quatro projetos não são todos iguais — e o que isso te ensina

> **Para quem é este capítulo:** para você, que começou a construir software
> porque o agente destravou o caminho. Não é preciso ser desenvolvedor para
> entender as escolhas aqui. É preciso entender as **consequências** delas —
> porque são elas que decidem quanto você paga por mês, o que quebra quando você
> não está olhando, e quanto o agente consegue te ajudar.

---

## 1. A decisão que ninguém te conta que existe

Quando você pede ao agente *"cria um sistema de pedidos"*, ele escolhe uma stack
por você. Quase sempre uma boa. Mas ele escolheu — e você não participou.

Stack é o conjunto de tecnologias que sustenta o sistema: em que linguagem o
servidor é escrito, onde o dado mora, como a tela é construída, onde tudo isso
roda. A escolha não é sobre "qual é a melhor". É sobre **qual erra menos no seu
caso** — e "seu caso" inclui coisas que nenhum tutorial menciona: se você vai
cobrar por isso, se precisa rodar de madrugada, se você vai conseguir consertar
sozinho quando quebrar.

Neste programa você vai construir em **duas stacks diferentes, de propósito**.
Não para aprender duas tecnologias — para aprender a **escolher**.

---

## 2. As duas abordagens, em uma frase cada

**Abordagem A — Python no servidor, React na tela.**
O cérebro é escrito em Python (com FastAPI); a interface é React. São duas peças
que conversam por uma API. É a arquitetura mais comum em sistemas que fazem
contas, integram serviços e rodam rotinas.

**Abordagem B — tudo em JavaScript (Next.js).**
Uma peça só: a mesma linguagem escreve a tela e o servidor. É a arquitetura mais
comum em produtos que são, antes de tudo, uma interface.

Nos dois casos o banco é **Supabase**, a autenticação é Supabase, e cada
aplicação expõe seu **conector MCP** para os agentes. O que muda é o miolo.

> **Elas não têm o mesmo peso no programa.** A abordagem A é a **stack canônica**
> — a recomendação deste programa, e onde você constrói três dos quatro sistemas.
> A abordagem B entra **uma única vez**, de propósito, como excursão de
> contraste. A §7 explica a hierarquia sem rodeio.

---

## 3. O comparativo

| Critério | Python + FastAPI | Next.js (tudo em JS) |
|---|---|---|
| **Como a IA escreve** | ⭐ Muito bem. Python é a linguagem mais presente no treino dos modelos, e FastAPI mudou pouco em anos — código gerado hoje se parece com código de 2 anos atrás | ⚠️ Bem, mas com armadilha. Next.js mudou muito e rápido; o agente mistura jeitos de fazer de gerações diferentes. Parece certo e não funciona |
| **Estabilidade** | ⭐ Alta. Atualizar raramente quebra | ⚠️ Média. Mudanças grandes entre versões maiores |
| **Maturidade** | ⭐ FastAPI é padrão de mercado há anos | ⭐ Next.js também é — só evolui mais rápido |
| **Ecossistema** | ⭐ Imbatível em IA, dados, automação, integrações | ⭐ Imbatível em interface, componentes visuais, gráficos |
| **Segurança para quem não é dev** | ⭐ O servidor é servidor. Não existe fronteira para errar | ⚠️ Tela e servidor no mesmo arquivo: é fácil o agente vazar uma senha para o navegador sem avisar |
| **Performance** | ⭐ Ótima nesta escala | ⭐ Ótima nesta escala — *empate real* |
| **Escalabilidade** | ⭐ Escala bem; você controla | ⭐ Escala bem; a plataforma controla |
| **Tela responsiva ("snappy")** | ⭐ Igual | ⭐ Igual — depende da tela, não do servidor |
| **Deploy** | ⚠️ Precisa de servidor de verdade (VPS) | ⭐ Um clique na Vercel — *com uma pegadinha, ver §5* |
| **Rotinas agendadas** | ⭐ Livre. Roda de hora em hora, de minuto em minuto | ⚠️ Limitado nos planos baratos das plataformas |
| **Contrato da API** | ⭐ Gerado sozinho, nunca desatualiza | ⚠️ Você (ou o agente) mantém à mão |
| **Curva para não-dev** | ⚠️ Duas peças para entender | ⭐ Uma peça só |

**Leia a tabela assim:** não há coluna vencedora. Há cinco linhas em que uma
ganha claramente, cinco em que a outra ganha, e três empates. O trabalho é saber
**quais linhas importam no seu projeto**.

---

## 4. O critério que mais importa aqui: como a IA escreve em cada uma

Esta é a linha que quase nenhum comparativo na internet tem, porque quase nenhum
foi escrito para quem programa com agente. E é a que mais afeta você.

**O agente aprendeu com o que existia.** Se uma tecnologia mudou de forma
profunda nos últimos anos, o modelo viu as duas versões — a antiga e a nova — e
às vezes mistura. O código sai plausível, bem formatado, e **errado de um jeito
difícil de enxergar**.

Next.js passou por uma mudança dessas. Existem hoje duas formas bem diferentes de
escrever a mesma tela, e o agente às vezes começa numa e termina na outra. Para
um desenvolvedor experiente, isso é um aborrecimento de dez minutos. Para você, é
uma tarde perdida com uma mensagem de erro que não diz o que está errado.

Python com FastAPI não tem esse problema na mesma intensidade. A forma de
escrever é estável há anos, e quando quebra, a mensagem de erro aponta a linha.

> **Isso não significa "use Python sempre".** Significa que, ao escolher a
> abordagem B, você precisa ser **específico com o agente sobre a versão** — e
> vai aprender exatamente como fazer isso no módulo que usa Next.js.

Duas defesas que valem em qualquer stack, e que você vai praticar:
1. **Diga a versão no pedido.** "Next.js 15, App Router" em vez de "Next.js".
2. **Peça para o agente rodar antes de dizer que terminou.** Código que não foi
   executado não está pronto — não importa quão convincente ele pareça.

---

## 5. Por que Next.js — e o que mais existe

### 5.1 Antes de tudo: Next.js não é "o frontend"

Confusão comum, e vale desfazer porque muda a conversa.

**React** é a biblioteca que desenha a tela. Sozinha, ela não sabe organizar
páginas, buscar dados nem falar com o banco. Por isso quase ninguém usa React
puro: usa-se React **dentro de um framework** que resolve o resto.

**Next.js é um desses frameworks — e ele também é servidor.** Escolher Next.js
não é escolher como a tela é feita; é escolher que o **servidor também será
JavaScript**. É uma decisão de arquitetura inteira, não de interface.

Nos módulos 01, 02 e 04 o servidor é Python. A tela deles é React — mas **não
precisa de Next.js**, porque não há servidor JavaScript para Next.js ser. Ali a
escolha certa é a mais simples possível:

> **Vite + React.** Vite é a ferramenta que monta o projeto e roda o servidor de
> desenvolvimento. Estável, rápida, quase sem conceitos novos. O resultado é um
> punhado de arquivos estáticos que qualquer hospedagem serve — inclusive a mais
> barata. Nenhum "servidor de frontend" para manter.

Então a pergunta "por que Next.js" só existe de fato **no módulo 03**, que é
onde o servidor vira JavaScript.

### 5.2 As alternativas reais

| Opção | O que é | Como a IA escreve | Curva p/ não-dev | Quando faz sentido |
|---|---|---|---|---|
| **Next.js** | Framework React full-stack | ⭐ Muita informação no treino — mas mistura gerações (§4) | ⚠️ Média | É o padrão de mercado; o que o agente produz sozinho |
| **Vite + React** *(sem servidor)* | Só a tela | ⭐ Muito bem, e é estável | ⭐ Baixa | **Quando o servidor é Python.** Nossos módulos 01/02/04 |
| **Vite + React + Hono** | Tela + um servidor JS mínimo | ⭐ Bem (React e servidores simples são muito representados) | ⭐ Baixa — sem fronteira mágica | JS no servidor **sem** a complexidade do Next |
| **React Router v7** *(ex-Remix)* | Framework React full-stack, mais próximo do "jeito web" | ⚠️ Menos material; e a fusão Remix→React Router bagunçou o treino | ⭐ Baixa — modelo mental mais simples | Quem quer full-stack React sem os enigmas do Next |
| **SvelteKit** | Framework full-stack, **não é React** | ⚠️ Bem menos material | ⭐ Muito baixa — o código é o mais legível de todos | Projeto novo, sozinho, sem compromisso com React |
| **Nuxt (Vue)** | Equivalente ao Next, no mundo Vue | ⚠️ Menos material que Next | ⭐ Baixa | Se você já sabe Vue |
| **Astro** | Focado em conteúdo (site, blog, landing) | ⭐ Bem | ⭐ Baixa | Site institucional — **não** para app com carrinho |
| **TanStack Start** | Full-stack React, novo | ❌ Pouquíssimo material — o agente inventa | ⚠️ Média | Ainda não, para este público |

### 5.3 A resposta honesta: por que Next.js no módulo 03

Aqui cabe uma admissão, porque ela é a lição.

Os pontos fortes de propaganda do Next.js — renderizar no servidor para o Google
achar, primeiro carregamento instantâneo, página pública veloz — **quase não
valem no módulo 03**. Catálogo e Pedidos é um sistema interno, atrás de login.
Não tem Google para agradar. Ou seja: se a decisão fosse puramente técnica,
`Vite + React + Hono` seria mais simples e igualmente capaz.

Ele foi escolhido por três razões que **não são técnicas, e são as que importam
para você**:

1. **É o que o agente entrega quando você não especifica.** Peça "um app de
   pedidos" e a chance de vir Next.js é altíssima. Aprender Next.js aqui é
   aprender a lidar com o que você vai receber na vida real — inclusive a
   reconhecer quando ele é exagero para o problema.
2. **É a stack JS com mais material no treino dos modelos.** Apesar da armadilha
   da §4, o agente ainda escreve Next.js melhor do que qualquer outro framework
   JS full-stack — simplesmente porque viu muito mais.
3. **É a porta de entrada da lição de hospedagem.** As duas pegadinhas da §6 —
   uso comercial e rotina agendada — só aparecem de verdade quando você tenta
   publicar um Next.js na Vercel. É uma aula que se aprende publicando.

> **A lição por trás da escolha:** "melhor tecnologia" e "melhor escolha" são
> coisas diferentes. Às vezes você escolhe a opção mais popular não porque é a
> mais elegante, mas porque é a que **tem mais gente, mais exemplo e mais ajuda
> disponível** — inclusive dentro do agente. Popularidade é uma característica
> técnica quando você programa com IA.

### 5.4 A regra prática para escolher framework com um agente

Três perguntas, nesta ordem:

1. **Existe muito material público sobre isso?** Se a resposta for não, o agente
   vai inventar com confiança. Tecnologia nova e brilhante é o pior lugar para
   quem depende do agente. Esta pergunta vem primeiro.
2. **Mudou de forma profunda nos últimos dois anos?** Se sim, **diga a versão em
   todo pedido** — senão o agente mistura o antigo com o novo.
3. **É a coisa mais simples que resolve o meu problema?** Framework com servidor
   embutido, se você não precisa do servidor, é peso extra para carregar e mais
   lugar para errar.

---

## 6. Deploy e custo — onde a escolha vira dinheiro

Aqui a diferença sai do abstrato. Cada abordagem tem hospedagens naturais, e
elas custam diferente.

| Onde | Serve para | Ordem de grandeza | Cuidado |
|---|---|---|---|
| **Vercel** | Next.js | Plano grátis generoso; pago por usuário/mês | **O plano grátis proíbe uso comercial** |
| **VPS (Hostinger, Contabo, DigitalOcean)** | Python **e** Node | Dezenas de reais/mês, valor fixo | Você é o responsável: atualização, SSL, backup |
| **Railway / Render / Fly** | Python **e** Node | Cobrança por uso; começa barato | Conta cresce junto com o tráfego |
| **Supabase** | Banco, login, realtime — nos dois casos | Grátis para começar; pago quando crescer | O plano grátis **pausa** o banco após inatividade |

> ⚠️ **A pegadinha que derruba aluno.** O plano gratuito da Vercel é para uso
> **não comercial**. Se você vai cobrar do cliente, ou usar o sistema na sua
> própria empresa, você precisa do plano pago. Não é pirataria de fim de semana:
> é o termo de uso deles. Descobrir isso depois de entregar ao cliente é ruim.
> *(Confirme os valores e limites atuais antes de decidir — eles mudam.)*

**A segunda pegadinha: rotina agendada.** A promessa deste programa é *"funciona
com a sua máquina desligada"* — o lembrete dispara às 8h, a cobrança avisa no
vencimento. Nos planos baratos das plataformas serverless, rotina agendada é
limitada: poucas execuções, frequência baixa. Um VPS de algumas dezenas de reais
roda de minuto em minuto sem reclamar.

Isso tem uma consequência de arquitetura direta, e você vai vê-la acontecer:
**é o requisito de agendamento, não a linguagem, que decide onde o sistema mora.**

**Terceira via, que usamos aqui:** deixar as rotinas no **próprio banco**
(Supabase roda tarefas agendadas). Aí a aplicação fica leve, hospedada onde for
mais barato, e o que precisa acordar sozinho acorda dentro do banco. É a solução
que aparece no programa quando o VPS não se justifica.

---

## 7. Onde cada abordagem entra no programa

| Módulo | Abordagem | Por que esta e não a outra |
|---|---|---|
| **01 · CRM** | Python + FastAPI | Você **já tem** este sistema em Python, da turma básica. A promessa é promover o que existe, não recomeçar. Além disso: migração de banco e resumo de reunião por IA são território de Python |
| **02 · Agenda** | Python + FastAPI | Fuso horário e horário de verão são a maior fonte de bug silencioso em agenda — Python tem as ferramentas mais seguras. E lembrete de hora em hora quer um servidor livre |
| **03 · Catálogo e Pedidos** | **Next.js** | **O módulo do contraste.** É o mais visual (catálogo, carrinho), não tem rotina agendada complexa, e o estoque atualiza na tela por evento. Onde a abordagem B mostra a força dela com o menor risco |
| **04 · Financeiro** | Python + FastAPI | Dinheiro. JavaScript não tem tipo numérico exato nativo; erro de centavo em projeção de caixa é o defeito mais caro possível. Aqui a escolha não é preferência |

**Por que só um módulo na abordagem B.** Porque o objetivo é você **saber
escolher**, não virar especialista em duas stacks em oito semanas. Um módulo é
suficiente para você sentir na pele a diferença — o que é mais fácil, o que é
mais chato, e onde o agente escorrega.

> **A recomendação do programa, dita sem rodeio:** para os seus próprios
> projetos, comece pela **stack canônica** — FastAPI + Supabase + Vite/React,
> publicada em VPS. É a combinação em que o agente erra menos, em que a
> segurança não depende de você revisar código, e em que o custo é fixo e o uso
> comercial é livre. A abordagem B você aprende aqui para **reconhecer e
> avaliar** — porque é o que o agente te entrega quando você não especifica —
> não porque seja a primeira escolha.

---

## 8. O que **não** muda entre as duas

Esta é a parte tranquilizadora, e é o motivo de a mistura funcionar:

- **O banco é o mesmo** — Supabase, nos quatro.
- **A segurança é a mesma** — as regras de acesso (RLS) moram **dentro do
  banco**, não no código. Isso importa muito para você: mesmo que o agente
  cometa um erro na aplicação, o banco continua recusando o que não é seu. É
  cinto de segurança que não depende de você revisar código.
- **O conector MCP é o mesmo** — os quatro expõem as mesmas ferramentas para os
  agentes, do mesmo jeito, com a mesma autenticação. Um agente conversa com os
  quatro sem saber em que linguagem cada um foi escrito.
- **O contrato entre os módulos é o mesmo** — os eventos que um sistema manda
  para o outro têm o mesmo formato nos quatro.

É por isso que dá para misturar sem virar bagunça: **as fronteiras são iguais.**
Só o miolo muda.

---

## 9. Como decidir no seu próximo projeto

O que você leva deste capítulo não é "Python para X, Next.js para Y". É um
roteiro de cinco perguntas, na ordem em que importam:

1. **Tem dinheiro envolvido em conta?** Cálculo financeiro, projeção, juros?
   → puxa para Python.
2. **Precisa acordar sozinho?** Lembrete, cobrança, relatório de madrugada?
   → puxa para servidor próprio (VPS) ou rotina dentro do banco. Confira o
   limite do plano grátis **antes** de escolher a hospedagem.
3. **É comercial?** Vai cobrar, ou usar na sua empresa?
   → confira o termo de uso do plano grátis. Isso elimina opções.
4. **O valor está na tela ou na lógica?** Se o produto *é* a interface, a
   abordagem B economiza tempo real. Se a interface é a janela de um motor,
   a abordagem A separa melhor.
5. **Você consegue consertar sozinho às 23h?** Escolha o que você entende — não
   o que tem o benchmark mais bonito. Sistema que você não sabe consertar é
   sistema que fica quebrado.

> **A regra que resume tudo:** a melhor stack para você é aquela em que **o
> agente erra menos e você percebe mais rápido quando ele erra**. Todo o resto —
> performance, escalabilidade, elegância — só começa a importar depois que o
> sistema está no ar, funcionando, com gente usando.
