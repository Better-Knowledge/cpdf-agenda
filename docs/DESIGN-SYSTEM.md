# Design System — Mini CRM

> **Nome do sistema:** *Agentes e Sistemas com IA*
> **Versão:** 2.0 · 22/08/2026
> **Implementação de referência:** [`public/styles.css`](../public/styles.css)

---

## 1. Princípios

**1. Papel, não painel de controle.** O CRM parece um caderno de trabalho bem impresso: fundo creme,
tipografia com serifa nos números, textura sutil de grade. Não parece um dashboard corporativo de
azul e cinza — e essa escolha é deliberada, porque o produto é usado todo dia por uma pessoa só.

**2. Uma cor de ação.** O terracota (`--ac-orange`) marca **apenas** o que exige atenção ou ação:
botão primário, aba ativa, número de KPI, foco de campo. Se tudo é laranja, nada é.

**3. Hierarquia por peso, não por caixa.** Ao invés de empilhar bordas e painéis, a hierarquia vem do
tamanho tipográfico, do espaço em volta e da elevação quente. Menos linhas, mais respiro.

**4. Serifa carrega o número.** Libre Baskerville em itálico aparece nos valores, contagens e
destaques — dá peso editorial ao dado sem precisar de negrito berrante.

**5. Sem dependência externa.** Nenhum framework de CSS, nenhuma biblioteca de gráficos, nenhum CDN
de script. Os gráficos são SVG gerado em JavaScript. Isso mantém `script-src` em `'self'` — decisão
de segurança que o design respeita, não contorna.

> **Ressalva honesta sobre a CSP.** A política atual da v1 **não** é tão restritiva quanto esta
> frase sugere: ela carrega `'unsafe-inline'` em `script-src` e `script-src-attr`, porque os
> elementos gerados usam `onclick`, `ondragstart` e `ondrop` em atributo. Isso anula boa parte da
> proteção contra XSS que a CSP deveria oferecer. A correção é RNF-16 do
> [PRD de Reconstrução](PRD-Reconstrucao-CRM.md): eventos por **delegação**, um listener por região,
> `data-*` para identificar o alvo — e aí `'unsafe-inline'` cai. Até lá, o escape de saída é a
> **única** linha de defesa (ver §6).

**6. Todo estado tem forma.** Vazio, carregando, erro e sucesso são estados desenhados. Uma lista
vazia mostra frase em itálico serifado, nunca um retângulo em branco.

---

## 2. Tokens

Todos os tokens vivem em `:root` como custom properties. **Nenhum valor cru de cor, raio ou sombra
deve aparecer em regra de componente** — se falta um token, cria-se o token.

### 2.1 Cores de marca

| Token | Valor | Uso |
|---|---|---|
| `--ac-orange` | `#E26546` | Terracota. Ação, foco, destaque, KPI |
| `--ac-cream` | `#F4F3EE` | Fundo da aplicação |
| `--ac-stone` | `#B1ADA1` | Texto de apoio, rótulos secundários |
| `--ac-graphite` | `#30302E` | Texto secundário |
| `--ac-ink` | `#1A1918` | Texto principal, superfícies invertidas |
| `--ac-cream-hover` | `#ECEAE2` | Hover em superfície creme |

### 2.2 Cores semânticas

| Token | Valor | Uso |
|---|---|---|
| `--bg` | `var(--ac-cream)` | Fundo da página |
| `--bg-elev` | `#FFFFFF` | Card, modal, dropdown |
| `--bg-sunk` | `#ECEAE2` | Trilho de barra, bloco de interação |
| `--fg` | `var(--ac-ink)` | Texto principal |
| `--fg-muted` | `var(--ac-graphite)` | Texto secundário |
| `--fg-soft` | `var(--ac-stone)` | Rótulo, placeholder, metadado |
| `--border` | `rgba(26,25,24,0.10)` | Borda padrão |
| `--border-2` | `rgba(26,25,24,0.16)` | Borda de controle e hover |
| `--accent` | `var(--ac-orange)` | Alias semântico da ação |

### 2.3 Cores de estado

| Token | Valor | Significado |
|---|---|---|
| `--success` | `#4F7A5A` | Verde-oliva. Ganho, valor fechado |
| `--warning` | `#D6A24E` | Âmbar. Aviso, base de dados insuficiente |
| `--danger` | `#C0432D` | Vermelho-tijolo. Atrasado, perdido, destrutivo |

**Fundos translúcidos de estado** (usados em tags, avisos e botões de perigo) seguem a fórmula
`rgba(<cor>, 0.08–0.14)` com borda em `0.30–0.35` da mesma cor. Nunca se usa a cor sólida como
fundo de bloco — só como texto, borda ou preenchimento de barra.

### 2.4 Tipografia

| Token | Família | Papel |
|---|---|---|
| `--font-sans` | Fira Sans | Interface: botões, abas, rótulos, títulos de bloco |
| `--font-serif` | Libre Baskerville | Números, valores, ênfase editorial (`<em>`) |
| `--font-body` | Inter | Corpo de texto, campos de formulário, listas |
| `--font-mono` | JetBrains Mono | Metadados técnicos, chave de API revelada |

**Escala tipográfica**

| Papel | Família | Tamanho | Peso | Tracking |
|---|---|---|---|---|
| Display da tela | sans | `clamp(34px, 5vw, 52px)` | 600 | `-0.025em` |
| Título de modal | sans | 30px | 600 | `-0.02em` |
| Número de KPI | serif | 46px (34px em métricas de valor) | 700 | — |
| Título de bloco | sans | 15px, caixa alta | 600 | `0.04em` |
| Eyebrow | sans | 13px, caixa alta | 500 | `0.22em` (`--tr-widest`) |
| Corpo | body | 15–16px | 400 | — |
| Rótulo de campo | sans | 12px, caixa alta | 500 | `0.06em` |
| Metadado | body/mono | 12–13px | 400 | — |
| Pílula de marca | sans | 11px, caixa alta | 400 | `0.22em` |

**Regra do itálico:** `<em>` dentro de títulos troca para a serifa em itálico e cor terracota. É a
assinatura visual do produto — "Mini *CRM*", "Seus *números*", "Funil de *vendas*". Use uma vez por
título, na palavra que carrega o significado.

### 2.5 Raios

| Token | Valor | Uso |
|---|---|---|
| `--r-2` | 4px | Item de dropdown, bloco de código |
| `--r-3` | 8px | Botão, campo, bloco de interação |
| `--r-4` | 12px | Item de lista, cartão do funil, busca |
| `--r-5` | 18px | Card de estatística, coluna do funil, modal, card de login |
| `--r-pill` | 999px | Tag, chip, aba, toast, trilho de barra |

### 2.6 Elevação

Sombras **quentes** — derivadas do tom de tinta, nunca do preto puro:

| Token | Valor | Uso |
|---|---|---|
| `--shadow-sm` | `0 1px 2px rgba(26,25,24,.06), 0 1px 1px rgba(26,25,24,.04)` | Repouso de card e item |
| `--shadow-md` | `0 4px 14px rgba(26,25,24,.08), 0 1px 2px rgba(26,25,24,.04)` | Hover de card e botão primário |
| `--shadow-lg` | `0 18px 48px rgba(26,25,24,.16), 0 3px 8px rgba(26,25,24,.06)` | Modal, dropdown, toast |

### 2.7 Movimento

| Token | Valor |
|---|---|
| `--ease` | `cubic-bezier(0.22, 1, 0.36, 1)` |

| Duração | Aplicação |
|---|---|
| 150–180 ms | Hover, foco, cor |
| 200–300 ms | Entrada de modal, dropdown, toast |
| 500 ms | Preenchimento de barra do dashboard |

**Animações nomeadas:** `surge` (tela entra subindo 12px), `fade` (fundo do modal), `pop` (modal e
dropdown escalam de 0.97), `rise` (toast sobe 14px).

> Movimento nunca comunica sozinho. Se a animação for suprimida por preferência do sistema, a
> informação continua legível.

### 2.8 Espaçamento

Grade base de **4px**. Valores usados: 4 · 6 · 8 · 10 · 12 · 14 · 16 · 18 · 20 · 22 · 24 · 28 ·
36 · 40 · 48 · 80.

| Contexto | Valor |
|---|---|
| Padding do topo | `18px 40px` |
| Padding do main | `48px 40px 80px`, `max-width: 1320px`, centralizado |
| Gap de grade (KPIs, kanban, dashboard) | 16px |
| Gap de lista | 10px |
| Margem inferior de bloco | 36px |
| Padding de card | 22px 24px |
| Padding de modal | 36px |

---

## 3. Componentes

### 3.1 Botão — `.btn`

| Variante | Aparência | Uso |
|---|---|---|
| Padrão | Fundo branco, borda `--border-2`, texto `--fg` | Ação secundária |
| `.primario` | Fundo terracota, texto branco | **Uma por tela.** Salvar, entrar, criar |
| `.perigo` | Transparente, texto e borda `--danger` | Excluir, revogar |

Padding `10px 18px`, raio `--r-3`, fonte sans 14px/500. **Hover:** eleva 1px, ganha
`--shadow-sm` e escurece a borda. **Foco:** anel de 3px em `rgba(226,101,70,0.12)` — nunca
`outline: none` sem substituto.

### 3.2 Aba — `.aba`

Pílula sem borda. Repouso: texto `--fg-muted`. Hover: fundo `--ac-cream-hover`. **Ativa:** fundo
`--ac-ink` com texto creme — inversão total, não apenas mudança de cor. A aba ativa é o elemento
mais escuro do topo, e isso é intencional: localização antes de decoração.

### 3.3 Card de estatística — `.stat-card`

```
┌──────────────────────────┐
│  46px serif terracota    │  ← .stat-num
│  RÓTULO EM CAIXA ALTA    │  ← .stat-lbl  (12px, tracking .14em, --fg-soft)
│  contexto em 12px        │  ← .stat-ctx  (opcional, com .destaque em terracota)
└──────────────────────────┘
```

Fundo `--bg-elev`, raio `--r-5`, padding `22px 24px`, `--shadow-sm`. A variante `.alerta` pinta o
número em `--danger`. Valores monetários usam `.stat-num.medio` (34px) para não estourar a caixa.

### 3.4 Item de lista — `.item`

Linha com informação à esquerda (nome em sans 600 + subtítulo em `--fg-soft`) e ação à direita
(máx. 46% de largura, com a data em terracota 600). Hover desliza **3px para a direita** — o
movimento lateral sinaliza "isto abre algo", diferente do card do funil, que sobe.

### 3.5 Cartão do funil — `.cartao`

Nome, empresa e valor em serifa itálica verde. `cursor: grab`, virando `grabbing` no arraste.
Arrastando: opacidade 0.35 e rotação de 1.5°. A coluna de destino recebe `.dragover` — borda
terracota e fundo `rgba(226,101,70,0.06)`.

### 3.6 Coluna do funil — `.coluna`

Fundo branco a 50% de opacidade, raio `--r-5`, altura mínima de 220px para nunca colapsar quando
vazia. Cabeçalho com o nome da etapa em caixa alta e a contagem em serifa itálica terracota.

### 3.7 Modal — `.modal`

Fundo `rgba(26,25,24,0.45)` com `backdrop-filter: blur(4px)`. Conteúdo de até 660px, alinhado ao
topo com 48px de folga (nunca centralizado verticalmente — fichas longas rolam). Botão de fechar
no canto superior direito, `×` de 28px. Fecha por clique no fundo e por `Esc`.

### 3.8 Campo de formulário — `.campo`

Rótulo em caixa alta 12px acima do controle. Controle com fundo `--bg` (creme, não branco — o campo
"afunda" no card branco), borda `--border-2`, raio `--r-3`. Foco: borda terracota + anel de 3px.
`.linha` agrupa dois campos lado a lado, colapsando para um em telas estreitas.

### 3.9 Tags e chips

| Classe | Aparência |
|---|---|
| `.tag.ganho` | Fundo verde a 14%, texto `--success` |
| `.tag.perdido` | Fundo vermelho a 12%, texto `--danger` |
| `.chip` | Contorno neutro, texto `--fg-muted` |
| `.chip.accent` | Contorno e texto terracota |
| `.badge-ia` | Fundo terracota a 14%, texto terracota, 10px, tracking `0.1em` |

O `.badge-ia` é o marcador de proveniência: toda interação gerada por agente o carrega. É requisito
de auditoria expresso em pixels — o usuário nunca precisa adivinhar se um texto foi escrito por uma
pessoa.

### 3.10 Toast — `.toast`

Pílula fixa 28px acima da base, centralizada. Fundo `--ac-ink` com texto creme; `.erro` inverte para
fundo `--danger`. Entra com `rise`, sai após ~3s. É o retorno padrão de **toda** ação bem-sucedida.

### 3.11 Dropdown do usuário — `.dropdown`

Ancorado à direita do gatilho, 8px abaixo. Largura mínima 190px, `--shadow-lg`. Item em hover ganha
fundo creme e texto terracota. Fecha por clique fora e por `Esc`.

### 3.12 Chave revelada — `.key-revelada`

Bloco de aviso terracota a 8% contendo o segredo em fundo tinta com texto creme e fonte mono,
`user-select: all` para seleção em um clique. Aparece **uma única vez**, com o aviso de que não
será exibido de novo.

### 3.13 Estado vazio — `.vazio`

Texto em serifa itálica, cor `--fg-soft`. Frase humana e específica da lista: "Nada atrasado — dia
limpo." é resposta; "Sem resultados." é silêncio.

### 3.14 Aviso do dashboard — `.dash-aviso`

Faixa âmbar a 10% com borda a 35%. Usada quando a base de dados é pequena demais para a métrica ser
confiável. **Métrica sem contexto de confiabilidade é métrica que mente.**

---

## 4. Gráficos

Todos gerados como SVG em JavaScript, sem biblioteca.

| Tipo | Onde | Regra |
|---|---|---|
| Barras agrupadas | Ganhos × perdidos por mês | Grade em `--border`, 5 linhas horizontais |
| Linha | Receita acumulada, novos leads | Traço de 2px na cor da série |
| Barras horizontais | Funil por valor, origem dos leads | Trilho `--bg-sunk`, preenchimento na cor da série, valor à direita em serifa |

**Classes de texto dentro do SVG:** `.svg-rotulo` (11px, `--fg-soft`), `.svg-valor` (11.5px sans 600,
`--fg-muted`), `.svg-grade` (traço em `--border`).

**Cores de série:** terracota para o principal, `--success` para ganho, `--danger` para perdido,
`--ac-stone` para referência neutra. Toda série colorida tem legenda (`.legenda`) — cor nunca é o
único portador da informação.

---

## 5. Layout e responsividade

| Faixa | Comportamento |
|---|---|
| ≥ 901px | Kanban e KPIs em 4 colunas; dashboard em 2 colunas; topo em linha única |
| 561–900px | Kanban e KPIs em 2 colunas; dashboard em 1 coluna; topo quebra em linhas; padding do main cai para 20px |
| ≤ 560px | Tudo em 1 coluna |

`main` limita-se a 1320px e centraliza. O corpo **nunca** rola horizontalmente; conteúdo largo
(tabelas, SVG) rola dentro do próprio contêiner.

---

## 6. Renderização segura

Os componentes deste sistema são montados com `innerHTML` a partir de dados do banco — e esses dados
podem ter sido escritos por um **agente de IA**, não por uma pessoa de confiança. Um lead criado por
MCP com `nome: "<img src=x onerror=...>"` executaria script na sessão de quem abrisse a tela.

| Regra | Como |
|---|---|
| **Todo dado dinâmico passa por escape** antes de entrar no DOM | Uma função única (`esc()`) converte `&`, `<`, `>` e `"` em entidades |
| Vale para **tudo** que veio do banco | Nome, empresa, cargo, origem, texto de interação, rótulo de chave, mensagem de erro da API |
| Números e datas formatados também | Passam por formatador próprio, que só produz caracteres seguros |
| Valor em atributo HTML sempre entre aspas | `data-id="${c.id}"`, nunca sem aspas |
| Nunca interpolar dado do usuário dentro de `<script>` ou de handler | É o caso que nenhum escape de HTML resolve |

```js
function esc(s) {
  return (s || '').replace(/[&<>"]/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]
  ));
}
```

> Esta é a **defesa que não aparece na tela** — e por isso a mais fácil de esquecer numa
> reconstrução: nada quebra quando se omite. Enquanto a CSP carregar `'unsafe-inline'` (§1,
> ressalva), ela é a única barreira entre um campo de texto e a execução de script na sessão do
> admin.

---

## 7. Acessibilidade

| Requisito | Como se cumpre |
|---|---|
| Contraste | Texto principal `#1A1918` sobre `#F4F3EE` ≈ 15:1. Terracota sobre creme ≈ 3.9:1 — **usar apenas em texto ≥ 18px ou peso ≥ 600**, nunca em corpo de texto |
| Foco visível | Anel de 3px terracota em todo elemento focável. `outline: none` só com substituto |
| Teclado | Todo fluxo navegável por Tab. `Esc` fecha modal e dropdown. Enter envia formulário |
| Alvo de toque | Mínimo de 40px de altura em controles interativos |
| Rótulos | Todo campo tem `<label>`. Botão só com ícone tem `aria-label` (ex.: fechar do modal) |
| Cor não é único sinal | Estado sempre acompanhado de texto ou ícone (tag "Ganho", ponto + rótulo "Atrasados") |
| Movimento | Animações são decorativas; respeitar `prefers-reduced-motion` |
| Idioma | `<html lang="pt-BR">` |

> **Dívida conhecida:** arrastar-e-soltar no funil não tem equivalente por teclado. A ficha do
> cliente oferece o mesmo resultado por formulário — esse é o caminho acessível, e ele precisa
> continuar existindo.

---

## 8. Escrever no produto

O texto é parte do design.

| Regra | Sim | Não |
|---|---|---|
| Português direto, sem jargão | "Nada atrasado — dia limpo." | "Nenhum registro encontrado." |
| Segunda pessoa, tom de colega | "Arraste os cartões conforme o cliente avança." | "O usuário deve arrastar os cartões." |
| Erro diz o que fazer | "A senha precisa de pelo menos 8 caracteres" | "Erro de validação" |
| Rótulo curto em caixa alta | `PRÓXIMA AÇÃO` | `Qual é a próxima ação?` |
| Título com uma ênfase | "Seus *números*" | "Seus *números* de *vendas*" |

Mensagens de erro da API são exibidas ao usuário **tal como vêm do servidor** — por isso elas são
escritas em português, para pessoas, e não em código técnico.

---

## 9. Regras para quem for estender

1. **Novo componente reusa tokens.** Cor, raio, sombra e espaçamento saem de `:root`. Valor cru em
   regra de componente é revisão reprovada.
2. **Nenhum recurso externo.** Sem CDN de script, sem biblioteca de gráfico, sem framework de CSS. A
   CSP permite `'self'` em `script-src` e isso não muda por conveniência de tela.
3. **Todo dado dinâmico é escapado** antes de entrar no DOM (§6). Componente novo que monta HTML sem
   passar pelo escape é revisão reprovada — mesmo que o dado "venha do nosso banco".
4. **Sem handler inline.** Nada de `onclick` em atributo: use delegação de eventos com `data-*`. É o
   que permite à CSP dispensar `'unsafe-inline'`.
5. **Uma ação primária por tela.** Se aparecer a segunda, uma delas é secundária.
6. **Todo estado desenhado.** Vazio, carregando, erro e sucesso antes de considerar a tela pronta.
7. **Toda ação destrutiva confirma.** E é vermelha.
8. **A serifa é para dado.** Não vira texto de corpo nem rótulo de campo.
9. **Terracota é para ação e atenção.** Não vira cor de fundo de bloco nem de texto longo.

---

## 10. Referência rápida

```css
/* superfície padrão */
background: var(--bg-elev);
border: 1px solid var(--border);
border-radius: var(--r-5);
box-shadow: var(--shadow-sm);
padding: 22px 24px;

/* transição padrão */
transition: all 0.18s var(--ease);

/* foco padrão */
border-color: var(--ac-orange);
box-shadow: 0 0 0 3px rgba(226, 101, 70, 0.12);

/* título com ênfase */
/* <h1 class="display-tela">Seus <em>números</em></h1> */
```
