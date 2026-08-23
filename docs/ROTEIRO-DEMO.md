# Roteiro da demo final — Agenda Inteligente (módulo 02)

Vinte minutos, uma agenda vazia no começo e um sistema inteiro no fim. O
roteiro é escrito para ser executado ao vivo, na ordem, com o notebook do
apresentador podendo ser desligado no meio (e isso é parte da demonstração).

**O que a demo prova, em uma frase:** a aplicação nasceu agent-friendly pelo
contrato, não pelo conector — e por isso a mesma capacidade aparece na tela,
no `curl`, no WhatsApp e no cliente MCP, com autoridades diferentes.

---

## Antes de começar (10 min, fora do palco)

1. `.env` do VPS com `SESSAO_ATENDIMENTO_SECRET`, `AGENDA_CRYPTO_KEY`,
   `BASE_URL_PUBLICA` e `MCP_HOSTS_PERMITIDOS` preenchidos.
2. `make up` · `make migrate migrate-canal`.
3. Uma credencial administrativa e uma de atendimento:

   ```bash
   make credencial ORG=<uuid> NOME="Painel da demo" PAPEL=administrativo
   make credencial ORG=<uuid> NOME="Bot do canal"   PAPEL=atendimento
   ```

4. Canal no Telegram configurado e o bot ativo (tela **Canal** → *Ativar o bot*).
5. Dois clientes MCP abertos: um apontando para `/agenda/mcp` (atendimento) e
   outro para `/agenda/admin/mcp` (administração).

---

## Ato 1 — A equipe monta a agenda por conversa (4 min)

No cliente MCP **administrativo**:

> "Cria uma agenda para a Dra. Helena, atendimento de 50 minutos, e abre a
> semana dela de segunda a sexta das 9h às 18h, com almoço das 12h às 13h."

O que a plateia vê: `agenda_admin_recurso_salvar`, `agenda_admin_servico_salvar`
e `agenda_admin_grade_definir` — **três chamadas**, não quinze. A grade é
declarativa: o agente descreve a semana inteira e o servidor faz a diferença
numa transação.

**O ponto a dizer em voz alta:** listar → remover uma → criar duas é
exatamente a sequência em que um modelo esquece um passo. A API foi desenhada
para que ele não precise fazê-la.

Abra a tela **Grade e bloqueios**: está tudo lá. Nenhuma tela foi usada.

---

## Ato 2 — O cliente marca pelo WhatsApp (5 min)

Do celular de alguém da plateia, para o bot do Telegram:

> "oi, queria marcar com a Dra. Helena quinta de tarde"

O agente consulta os horários, oferece **três**, o cliente escolhe, e a
confirmação chega em seguida.

Coisas para mostrar na hora:

- **A data é repetida por extenso** antes de confirmar. Peça para alguém
  escrever "dia 5" e mostre que o agente **pergunta** em vez de adivinhar —
  o dia 5 deste mês já passou (mitigação do risco §16).
- Abra a tela **Agenda do dia**: o compromisso apareceu sem ninguém tocar nela.

---

## Ato 3 — O isolamento (3 min) · o momento mais importante

Com a credencial de **atendimento** (a mesma do bot), tente pelo `curl`:

```bash
curl -s https://SEU-DOMINIO/appointments?date=2027-03-11 \
  -H "Authorization: Bearer agk_…atendimento"        # 403 ESCOPO_INSUFICIENTE
curl -s https://SEU-DOMINIO/services -X POST \
  -H "Authorization: Bearer agk_…atendimento" -d '{…}' # 403 ESCOPO_INSUFICIENTE
```

E, no cliente MCP de atendimento, peça para cancelar um compromisso: a resposta
é *"vou encaminhar a um atendente"*, não um cancelamento.

**O que dizer:** autenticar não concede tudo. O bot que fala com o cliente
final alcança o compromisso **daquele** cliente e mais nada — e compromisso de
terceiro responde 404, não 403, porque 403 já confirmaria que existe.

---

## Ato 4 — Cancelamento, fila e a corrida por um horário (4 min)

1. Pela tela, cancele um compromisso da tarde.
2. Em segundos, quem estava na fila de espera para aquela janela recebe a
   oferta pelo WhatsApp.
3. Mostre a tela **Fila de espera**: o horário **continua livre na grade**.

**O ponto:** não há reserva. A mensagem de oferta diz isso ao cliente, com
todas as letras — quem confirmar primeiro leva. Prometer reserva seria uma
promessa que o produto não cumpre.

---

## Ato 5 — Onde mais o compromisso aparece (3 min)

- **Google Calendar** (tela *Calendários* → Conectar): o evento surge no
  calendário do celular em menos de um minuto. Marque uma reunião direto no
  Google e mostre que aquele horário **some** dos slots oferecidos.
- **Link público** (tela *Links*): abra `/app/agendar/<slug>` numa aba
  anônima, marque como um cliente qualquer, e mostre o compromisso caindo na
  agenda com origem `link público`.
- **Feed .ics**: crie um no modo *só "Ocupado"* e mostre o arquivo — a mesma
  agenda, sem um nome de cliente sequer.

---

## Ato 6 — O fecho: os números e o notebook desligado (2 min)

Abra a tela **Números**: quanto veio por conversa, ocupação da grade,
confirmações, faltas. Ali está a tese do módulo medida.

E então **feche o notebook**. Os lembretes de amanhã vão sair mesmo assim: os
jobs rodam no VPS, não na máquina de quem apresenta. Se der para deixar um
lembrete programado para o meio da apresentação, melhor ainda — ele chega no
celular da plateia enquanto você fala.

---

## Se algo der errado no palco

| Sintoma | O que é | Saída |
|---|---|---|
| Bot não responde | webhook do Telegram sem HTTPS público | tela *Canal* → *Ativar o bot* de novo |
| Tudo responde 401 | `SESSAO_ATENDIMENTO_SECRET` diferente entre canal e agenda | conferir o `.env`; é **um** valor nos dois |
| Google não atualiza | push com retry, ou conexão recusada | tela *Calendários*: se disser "reconecte", o Google revogou |
| Slot some sem motivo | busy-read achou reunião no Google | é o comportamento correto — mostre o evento lá |
| MCP responde 421 | `MCP_HOSTS_PERMITIDOS` sem o domínio | ajuste o `.env` e `make up` |
