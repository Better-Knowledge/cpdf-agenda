# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""`agenda-mcp` — o atendimento ao cliente final por conversa (PRD §14.1–14.4).

**O conector mais exposto do programa.** É ele que o cliente final aciona,
indiretamente, ao mandar uma mensagem no WhatsApp. Três consequências que
moldam este arquivo:

1. **Oito tools, e nenhuma administrativa.** Criar serviço, abrir grade,
   bloquear férias, ver o dia inteiro — nada disso existe aqui. Não é
   checagem de escopo: é ausência. As tools administrativas moram no outro
   endpoint (`agenda-admin-mcp`), e o que não existe não pode ser chamado por
   engano nem por injeção de prompt vinda da mensagem do cliente.

2. **A credencial é do cliente, não do bot.** O `Authorization` desta conexão
   é tipicamente o token de sessão `ats_…` que o `canal-service` cunhou depois
   de provar o endereço de quem escreveu (RF-19). Com ele, "meus
   compromissos" quer dizer os daquela pessoa, e compromisso de terceiro
   responde 404 — não porque a tool filtre, mas porque a agenda não entrega.

3. **Cancelar não é do agente.** Uma credencial de atendimento não tem
   `agenda:cancel`, e a tool existe justamente para transformar a recusa em
   encaminhamento legível: "isso vai para um humano", em vez de um 403 que o
   modelo tentaria contornar.

**Sem resources (§14.2).** O SDK não injeta o contexto da requisição em
resource de URI estática, e sem contexto não há `Authorization` do chamador —
este conector não tem credencial própria para substituí-lo. Servir
`agenda://servicos` exigiria guardar um token aqui, que é exatamente o que a
etapa 9 eliminou. As mesmas leituras estão nas tools, que recebem contexto.

Datas em linguagem natural (`quando="quinta de tarde"`) são interpretadas em
`datas.py`, que **pergunta em vez de chutar** quando a expressão é ambígua —
a mitigação do risco §16 vive lá.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from . import agenda, datas, sessao
from .agenda import AgendaIndisponivel, AgendaRecusou

log = logging.getLogger("agenda_mcp")

INSTRUCOES = """\
Ferramentas para atender UM cliente por conversa: consultar horários livres,
marcar, remarcar, confirmar e entrar na fila de espera.

Autenticação: a credencial é o `Authorization: Bearer <token>` da própria
conexão. Numa conversa de canal ela é a sessão de atendimento cunhada para o
cliente que escreveu — por isso "meus compromissos" significa os dele, e o
telefone não precisa (nem deve) ser informado.

Como conduzir:
- consulte horários ANTES de prometer qualquer coisa (`agenda_consultar_slots`);
- **repita a data por extenso** antes de confirmar — toda saída traz
  `label_humano` pronto, use-o em vez de reformatar;
- data ambígua não se adivinha: a ferramenta devolve uma pergunta, faça-a;
- sem horário aceitável, ofereça a fila de espera (`agenda_fila_espera`) em vez
  de encerrar com "não tem";
- cancelar é irreversível e não é decisão sua: a agenda recusa e a conversa vai
  para um humano.
"""

mcp = MCPServer(
    name="agenda",
    title="Agenda Inteligente — atendimento",
    version="0.1.0",
    instructions=INSTRUCOES,
)


# ── Plumbing ─────────────────────────────────────────────────────────────────


def _autorizacao(ctx: Context) -> str:
    cabecalhos = ctx.headers or {}
    valor = cabecalhos.get("authorization") or cabecalhos.get("Authorization")
    if not valor:
        raise ToolError(
            "Esta conexão não apresentou credencial. O canal cunha um token de sessão "
            "(`ats_…`) a cada mensagem do cliente; configure o cliente MCP para "
            "repassá-lo em `Authorization: Bearer`."
        )
    return valor


async def _chamar(ctx: Context, metodo: str, rota: str, tool: str, corpo: Any | None = None) -> Any:
    autorizacao = _autorizacao(ctx)
    try:
        await sessao.quem_e(autorizacao, tool=tool)
        return await agenda.chamar(metodo, rota, autorizacao, tool=tool, corpo=corpo)
    except AgendaRecusou as e:
        raise ToolError(_traduzir(e)) from e
    except AgendaIndisponivel as e:
        raise ToolError(f"{e} Tente de novo em instantes; nada foi alterado.") from e


def _traduzir(e: AgendaRecusou) -> str:
    """A recusa, dita de um jeito que o agente saiba o que fazer.

    Dois casos ganham texto próprio porque a reação certa não é "tentar de
    novo com outros argumentos" — é falar com uma pessoa.
    """
    if e.code == "ESCOPO_INSUFICIENTE":
        return (
            f"{e.message} Esta conversa não tem autoridade para isso. Diga ao cliente "
            "que você vai encaminhar a um atendente e encerre a tentativa — não tente "
            "por outro caminho."
        )
    if e.code == "SESSAO_INVALIDA":
        return (
            "A sessão desta conversa expirou (ela vale 30 minutos a partir da mensagem "
            "do cliente). Peça que ele mande uma mensagem nova em vez de reaproveitar "
            "a sessão antiga."
        )
    return e.para_o_modelo()


def _sem_nulos(**campos: Any) -> dict[str, Any]:
    return {chave: valor for chave, valor in campos.items() if valor is not None}


def _intervalo(quando: str | None, de: str | None, ate: str | None) -> datas.Intervalo:
    """`quando` em português, ou `de`/`ate` em ISO — nesta ordem de preferência."""
    if quando:
        try:
            return datas.interpretar(quando, datetime.now(UTC))
        except datas.Ambigua as e:
            # Não é erro de payload: é uma pergunta para o cliente. O ToolError
            # carrega o texto pronto justamente para o agente repassá-lo.
            raise ToolError(e.pergunta) from e
    if de and ate:
        return datas.Intervalo(datetime.fromisoformat(de), datetime.fromisoformat(ate), "")
    raise ToolError(
        "Informe `quando` em português (ex.: \"quinta de tarde\", \"semana que vem\") "
        "ou o par `de`/`ate` em ISO 8601 com offset."
    )


# ── Leitura ──────────────────────────────────────────────────────────────────


@mcp.tool(
    title="Serviços oferecidos",
    description=(
        "O que este estabelecimento oferece, com duração e preço. O `service_id` "
        "daqui é obrigatório para consultar horários e para agendar — comece por "
        "aqui quando o cliente disser o que quer. Escopo exigido: `agenda:read`."
    ),
)
async def agenda_listar_servicos(ctx: Context) -> dict:
    resposta = await _chamar(ctx, "GET", "/services?limit=50", "agenda_listar_servicos")
    return {"servicos": resposta["items"]}


@mcp.tool(
    title="Consultar horários livres",
    description=(
        "Os horários realmente livres para um serviço, já descontando duração, "
        "folgas, bloqueios, compromissos existentes e a agenda externa do "
        "profissional. **Chame sempre antes de prometer horário**, e sempre que o "
        "cliente mencionar um dia ou período.\n\n"
        "Prefira `quando` em português — \"quinta de tarde\", \"amanhã cedo\", "
        "\"semana que vem\", \"12/09\". Se a expressão for ambígua (\"dia 5\" já "
        "passou neste mês, por exemplo), a ferramenta devolve a **pergunta** a fazer "
        "ao cliente em vez de adivinhar: faça a pergunta.\n\n"
        "Retorno vazio não é ponto final: amplie o período ou ofereça a fila de "
        "espera. Cada horário vem com `label_humano` — use exatamente esse texto ao "
        "falar com o cliente, e repita a data antes de confirmar. "
        "Escopo exigido: `agenda:read`."
    ),
)
async def agenda_consultar_slots(
    ctx: Context,
    service_id: Annotated[str, Field(description="Serviço desejado (de `agenda_listar_servicos`)")],
    quando: Annotated[
        str | None,
        Field(description='Período em português: "quinta de tarde", "semana que vem"'),
    ] = None,
    de: Annotated[str | None, Field(description="Alternativa: início em ISO 8601 com offset")] = None,
    ate: Annotated[str | None, Field(description="Alternativa: fim em ISO 8601 com offset")] = None,
    limit: Annotated[int, Field(description="Quantos horários no máximo", le=50)] = 20,
) -> dict:
    intervalo = _intervalo(quando, de, ate)
    rota = (
        f"/slots?service_id={service_id}&from={intervalo.de.isoformat()}"
        f"&to={intervalo.ate.isoformat()}&limit={limit}"
    )
    slots = await _chamar(ctx, "GET", rota, "agenda_consultar_slots")
    return {
        "periodo_consultado": intervalo.label or f"{intervalo.de} a {intervalo.ate}",
        "livres": slots,
        "sugestao": (
            "Nenhum horário livre nesse período. Ofereça outro período ou a fila de "
            "espera (agenda_fila_espera) — não encerre com 'não tem'."
            if not slots
            else "Ofereça no máximo 3 opções por vez e repita a data por extenso."
        ),
    }


@mcp.tool(
    title="Compromissos deste cliente",
    description=(
        "O que **este** cliente tem marcado, do mais próximo em diante. Numa conversa "
        "de canal o telefone é desnecessário: a sessão já diz de quem se trata, e "
        "informar outro não dá acesso a mais nada. Use para responder \"o que eu "
        "tenho marcado?\" e para achar o `appointment_id` antes de remarcar, "
        "confirmar ou cancelar. Escopo exigido: `agenda:read`."
    ),
)
async def agenda_meu_dia(
    ctx: Context,
    telefone: Annotated[
        str | None,
        Field(description="Só fora de uma sessão de atendimento; ignorado dentro dela"),
    ] = None,
) -> dict:
    rota = "/appointments/meus" + (f"?telefone={telefone}" if telefone else "")
    compromissos = await _chamar(ctx, "GET", rota, "agenda_meu_dia")
    return {
        "compromissos": compromissos,
        "resumo": (
            "Nenhum compromisso futuro — ofereça agendar."
            if not compromissos
            else f"{len(compromissos)} compromisso(s) futuro(s)."
        ),
    }


# ── Escrita ──────────────────────────────────────────────────────────────────


@mcp.tool(
    title="Agendar",
    description=(
        "Marca o horário para este cliente. Use um `inicio` que tenha vindo de "
        "`agenda_consultar_slots` — inventar horário produz recusa.\n\n"
        "Se o horário tiver sido tomado no meio da conversa, a recusa já traz as **3 "
        "alternativas mais próximas**: ofereça-as na mesma resposta, sem precisar "
        "consultar de novo.\n\n"
        "Numa sessão de atendimento, `cliente_telefone` é opcional e ignorado — quem "
        "responde é o cliente da conversa. Confirme a data por extenso antes de "
        "chamar. Escopo exigido: `agenda:write`."
    ),
)
async def agenda_agendar(
    ctx: Context,
    service_id: Annotated[str, Field(description="Serviço desejado")],
    inicio: Annotated[str, Field(description="Horário escolhido, ISO 8601 com offset")],
    cliente_nome: Annotated[str, Field(description="Como o cliente quer ser chamado")],
    cliente_telefone: Annotated[
        str | None, Field(description="Só fora de uma sessão de atendimento")
    ] = None,
    observacoes: Annotated[str | None, Field(description="Recado do cliente ao prestador")] = None,
) -> dict:
    corpo = _sem_nulos(
        service_id=service_id,
        inicio=inicio,
        cliente_nome=cliente_nome,
        cliente_telefone=cliente_telefone,
        observacoes=observacoes,
    )
    ap = await _chamar(ctx, "POST", "/appointments", "agenda_agendar", corpo)
    return {
        "agendado": True,
        "compromisso": ap,
        "para_falar": f"Marcado: {ap.get('label_humano')}. Você receberá a confirmação por aqui.",
    }


@mcp.tool(
    title="Remarcar",
    description=(
        "Move um compromisso para outro horário **atomicamente**: ou o novo horário é "
        "reservado e o antigo liberado na mesma operação, ou nada muda. Nunca existe "
        "um estado no meio.\n\n"
        "Consulte horários livres antes e confirme a nova data por extenso com o "
        "cliente. Horário novo ocupado devolve as 3 alternativas mais próximas. "
        "Escopo exigido: `agenda:write`."
    ),
)
async def agenda_reagendar(
    ctx: Context,
    appointment_id: Annotated[str, Field(description="Compromisso a mover (de `agenda_meu_dia`)")],
    novo_inicio: Annotated[str, Field(description="Novo horário, ISO 8601 com offset")],
    motivo: Annotated[str | None, Field(description="Fica no histórico")] = None,
) -> dict:
    ap = await _chamar(
        ctx,
        "POST",
        f"/appointments/{appointment_id}/reschedule",
        "agenda_reagendar",
        _sem_nulos(novo_inicio=novo_inicio, motivo=motivo),
    )
    return {
        "reagendado": True,
        "compromisso": ap,
        "para_falar": f"Remarcado para {ap.get('label_humano')}. O horário anterior já foi liberado.",
    }


@mcp.tool(
    title="Confirmar presença",
    description=(
        "Registra que o cliente confirmou que vem. É a resposta certa quando ele diz "
        "\"confirmo\", \"vou sim\", \"tá certo\" para um lembrete. Confirmar não muda "
        "horário nem libera nada — é seguro e reversível por remarcação. "
        "Escopo exigido: `agenda:write`."
    ),
)
async def agenda_confirmar(
    ctx: Context,
    appointment_id: Annotated[str, Field(description="Compromisso confirmado pelo cliente")],
) -> dict:
    ap = await _chamar(
        ctx, "POST", f"/appointments/{appointment_id}/confirm", "agenda_confirmar"
    )
    return {"confirmado": True, "compromisso": ap, "para_falar": "Presença confirmada, obrigado!"}


@mcp.tool(
    title="Entrar na fila de espera",
    description=(
        "Quando não há horário aceitável, isto é o que se oferece — **nunca** encerre "
        "a conversa com \"não tem vaga\". O cliente entra na fila para uma **janela** "
        "(\"quinta à tarde\"), não para um horário exato: quem quer um horário livre "
        "simplesmente agenda.\n\n"
        "Diga ao cliente como funciona: se alguém cancelar num horário compatível, "
        "ele recebe a oferta por aqui e tem um prazo para responder. **O horário não "
        "fica reservado** nesse meio-tempo — quem confirmar primeiro leva. "
        "Escopo exigido: `agenda:write`."
    ),
)
async def agenda_fila_espera(
    ctx: Context,
    service_id: Annotated[str, Field(description="Serviço desejado")],
    cliente_nome: Annotated[str, Field(description="Como o cliente quer ser chamado")],
    quando: Annotated[
        str | None, Field(description='Janela desejada em português: "quinta à tarde"')
    ] = None,
    janela_inicio: Annotated[str | None, Field(description="Alternativa: ISO 8601 com offset")] = None,
    janela_fim: Annotated[str | None, Field(description="Alternativa: ISO 8601 com offset")] = None,
    cliente_telefone: Annotated[
        str | None, Field(description="Só fora de uma sessão de atendimento")
    ] = None,
) -> dict:
    intervalo = _intervalo(quando, janela_inicio, janela_fim)
    corpo = _sem_nulos(
        service_id=service_id,
        cliente_nome=cliente_nome,
        cliente_telefone=cliente_telefone,
        janela_inicio=intervalo.de.isoformat(),
        janela_fim=intervalo.ate.isoformat(),
    )
    entrada = await _chamar(ctx, "POST", "/waitlist", "agenda_fila_espera", corpo)
    return {
        "na_fila": True,
        "entrada": entrada,
        "para_falar": (
            f"Coloquei você na fila para {intervalo.label or 'a janela pedida'}. Se vagar, "
            "eu aviso por aqui — mas o horário não fica reservado: quem responder "
            "primeiro fica com ele."
        ),
    }


# ── A ação que não é do agente ───────────────────────────────────────────────


class ConfirmacaoDeCancelamento(BaseModel):
    confirmar: Annotated[bool, Field(description="Sim, cancelar e liberar o horário")]


@mcp.tool(
    title="Cancelar (exige confirmação humana)",
    description=(
        "Cancelar libera o horário para outra pessoa na hora e **não tem volta**. Por "
        "isso não é decisão do agente.\n\n"
        "Numa conversa de canal, a credencial de atendimento não tem o escopo "
        "`agenda:cancel`: a chamada é recusada e o certo é dizer ao cliente que um "
        "atendente vai cuidar disso. Não tente contornar por outro caminho — remarcar "
        "não é cancelar.\n\n"
        "Onde há autoridade para cancelar, a confirmação humana ainda é obrigatória: "
        "a primeira chamada devolve a prévia e pede o OK; só a segunda executa. "
        "Escopo exigido: `agenda:cancel`."
    ),
)
async def agenda_cancelar(
    ctx: Context,
    appointment_id: Annotated[str, Field(description="Compromisso a cancelar")],
    motivo: Annotated[str | None, Field(description="Fica no histórico")] = None,
    confirmation_token: Annotated[
        str | None, Field(description="Só na segunda chamada, quando a confirmação veio por fora")
    ] = None,
) -> dict:
    rota = f"/appointments/{appointment_id}/cancel"
    corpo = _sem_nulos(motivo=motivo, confirmation_token=confirmation_token)
    autorizacao = _autorizacao(ctx)
    await sessao.quem_e(autorizacao, tool="agenda_cancelar")

    try:
        cancelado = await agenda.chamar(
            "POST", rota, autorizacao, tool="agenda_cancelar", corpo=corpo
        )
        return {"cancelado": True, "compromisso": cancelado}
    except AgendaRecusou as e:
        if e.code != "CONFIRMACAO_NECESSARIA":
            raise ToolError(_traduzir(e)) from e
        previa = e.extra.get("previa", {})
        token = e.extra.get("confirmation_token")
    except AgendaIndisponivel as e:
        raise ToolError(f"{e} Nada foi alterado.") from e

    pergunta = (
        f"Cancelar o horário de {previa.get('cliente', 'este cliente')} em "
        f"{previa.get('horario', '—')}? O horário volta para a grade na hora e pode ser "
        "ocupado por outra pessoa — não dá para desfazer."
    )

    if getattr(ctx.client_capabilities, "elicitation", None) is None:
        return {
            "cancelado": False,
            "confirmacao_necessaria": True,
            "previa": previa,
            "confirmation_token": token,
            "como_prosseguir": (
                "Mostre a prévia a uma pessoa responsável. Com o sim dela, chame esta "
                "ferramenta de novo com o mesmo appointment_id e o confirmation_token "
                "acima (expira em 5 minutos)."
            ),
        }

    resposta = await ctx.elicit(pergunta, ConfirmacaoDeCancelamento)
    if resposta.action != "accept" or not resposta.data.confirmar:
        return {"cancelado": False, "motivo": "A confirmação foi recusada — nada mudou.", "previa": previa}

    try:
        cancelado = await agenda.chamar(
            "POST", rota, autorizacao, tool="agenda_cancelar",
            corpo={**corpo, "confirmation_token": token},
        )
    except AgendaRecusou as e:
        raise ToolError(_traduzir(e)) from e
    return {"cancelado": True, "compromisso": cancelado}
