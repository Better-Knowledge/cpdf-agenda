"""`agenda-admin-mcp` — a equipe operando a plataforma por conversa (PRD §14.5).

**Por que um servidor separado do `agenda-mcp` de atendimento.** Com um só, a
separação de papéis dependeria de cada tool *lembrar* de conferir escopo — e
uma tool nova, escrita com pressa, esqueceria. Com dois, as tools
administrativas simplesmente **não existem** no endpoint que o agente de
atendimento alcança. A fronteira vira topologia, não disciplina.

**Onze tools, não vinte e duas.** O teto do programa é 15 por servidor
(`00` §5.9), mas a razão real é outra: cada CRUD completo (listar → remover
uma → criar duas) é um roteiro em que o modelo esquece um passo. As operações
aqui são **declarativas** — `salvar` cria-ou-altera, `grade_definir` descreve a
semana inteira — e o servidor faz a diferença numa transação.

**O conector não autoriza nada.** Ver `agenda.py`.
"""

import logging
from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from . import agenda, sessao
from .agenda import AgendaIndisponivel, AgendaRecusou

log = logging.getLogger("agenda_admin_mcp")

INSTRUCOES = """\
Ferramentas administrativas da Agenda Inteligente: catálogo, grade de trabalho,
bloqueios, visão do dia, fila de espera e credenciais de integração.

Autenticação: a credencial é o `Authorization: Bearer <token>` da própria
conexão MCP — o servidor a repassa à agenda sem alterar. Não existe token
guardado aqui, e nenhuma tool age em nome de outra organização.

O que estas ferramentas NÃO fazem: atender cliente final. Marcar, remarcar e
confirmar horário de um cliente acontece no canal (WhatsApp/Telegram), por uma
credencial de atendimento que alcança só o compromisso daquele cliente.

Convenções da agenda que valem em toda tool:
- horários em ISO 8601 **com offset** (America/Sao_Paulo na borda); toda saída
  de horário traz um `label_humano` pronto para falar com uma pessoa;
- erros trazem `hint` — é a metade que diz o que fazer a seguir, e às vezes já
  traz a saída (as 3 alternativas de horário, por exemplo);
- cancelar é irreversível e pede confirmação humana explícita.
"""

mcp = MCPServer(
    name="agenda-admin",
    title="Agenda Inteligente — administração",
    version="0.1.0",
    instructions=INSTRUCOES,
)


# ── Plumbing ─────────────────────────────────────────────────────────────────


def _autorizacao(ctx: Context) -> str:
    cabecalhos = ctx.headers or {}
    valor = cabecalhos.get("authorization") or cabecalhos.get("Authorization")
    if not valor:
        raise ToolError(
            "Esta conexão não apresentou credencial. Configure o cliente MCP com "
            "`Authorization: Bearer agk_…` — a chave é emitida na tela de "
            "Integrações da agenda ou por `make credencial` no servidor."
        )
    return valor


async def _chamar(ctx: Context, metodo: str, rota: str, tool: str, corpo: Any | None = None) -> Any:
    """Valida a sessão uma vez, chama a agenda e traduz a recusa.

    A tradução importa: um 403 cru faria o modelo tentar de novo com outros
    argumentos, achando que errou o payload. O texto da agenda já diz o que a
    credencial tem e o que a operação exige.
    """
    autorizacao = _autorizacao(ctx)
    try:
        await sessao.quem_e(autorizacao, tool=tool)
        return await agenda.chamar(metodo, rota, autorizacao, tool=tool, corpo=corpo)
    except AgendaRecusou as e:
        raise ToolError(e.para_o_modelo()) from e
    except AgendaIndisponivel as e:
        raise ToolError(f"{e} Tente de novo em instantes; nada foi alterado.") from e


def _sem_nulos(**campos: Any) -> dict[str, Any]:
    """Só o que foi informado vai no corpo — é o que faz `salvar` funcionar
    como alteração parcial sem apagar o que não foi mencionado."""
    return {chave: valor for chave, valor in campos.items() if valor is not None}


# ── Catálogo ─────────────────────────────────────────────────────────────────


@mcp.tool(
    title="Catálogo da organização",
    description=(
        "Serviços e recursos numa chamada só — comece por aqui. O `id` do serviço e "
        "o do recurso são a chave de quase todas as outras ferramentas. Recursos são "
        "o que não pode ser agendado duas vezes no mesmo horário: profissionais, "
        "salas, equipamentos. Escopo exigido: `agenda:read`."
    ),
)
async def agenda_admin_catalogo(
    ctx: Context,
    incluir_inativos: Annotated[
        bool, Field(description="Também traz serviços e recursos desativados")
    ] = False,
) -> dict:
    tool = "agenda_admin_catalogo"
    servicos = (await _chamar(ctx, "GET", "/services?limit=50", tool))["items"]
    recursos = (await _chamar(ctx, "GET", "/resources", tool))["items"]
    if incluir_inativos:
        # Duas chamadas em vez de um filtro "todos": desativar é reversível, e
        # sem enxergar o desativado ninguém acha o id para reativar.
        servicos += (await _chamar(ctx, "GET", "/services?ativo=false&limit=50", tool))["items"]
        recursos += (await _chamar(ctx, "GET", "/resources?ativo=false", tool))["items"]
    return {"servicos": servicos, "recursos": recursos}


@mcp.tool(
    title="Criar ou alterar serviço",
    description=(
        "Sem `service_id`, cadastra um serviço novo (nome e duração são obrigatórios). "
        "Com `service_id`, altera **só os campos informados**. Preço é string decimal "
        "em reais (\"80.00\"). Buffers são a folga em minutos antes e depois do "
        "atendimento. `resource_ids`, quando informado, substitui os vínculos atuais — "
        "é a lista completa de recursos que o serviço exige, não um acréscimo. "
        "Mudar a duração NÃO altera agendamentos já feitos, só os próximos. "
        "Para tirar um serviço da oferta use `ativo=false`: agendamentos e histórico "
        "ficam intactos. Escopo exigido: `agenda:admin`."
    ),
)
async def agenda_admin_servico_salvar(
    ctx: Context,
    nome: Annotated[str | None, Field(description="Nome como o cliente vê")] = None,
    duracao_min: Annotated[int | None, Field(description="Duração do atendimento em minutos")] = None,
    service_id: Annotated[str | None, Field(description="Informe para ALTERAR; omita para criar")] = None,
    preco: Annotated[str | None, Field(description='String decimal em reais, ex.: "80.00"')] = None,
    buffer_antes_min: Annotated[int | None, Field(description="Folga antes, em minutos")] = None,
    buffer_depois_min: Annotated[int | None, Field(description="Folga depois, em minutos")] = None,
    resource_ids: Annotated[
        list[str] | None, Field(description="Recursos que o serviço exige (substitui os atuais)")
    ] = None,
    ativo: Annotated[bool | None, Field(description="false tira o serviço da oferta")] = None,
) -> dict:
    corpo = _sem_nulos(
        nome=nome,
        duracao_min=duracao_min,
        preco=preco,
        buffer_antes_min=buffer_antes_min,
        buffer_depois_min=buffer_depois_min,
        resource_ids=resource_ids,
        ativo=ativo,
    )
    if service_id:
        return await _chamar(
            ctx, "PATCH", f"/services/{service_id}", "agenda_admin_servico_salvar", corpo
        )
    if not nome or not duracao_min:
        raise ToolError("Para criar um serviço, informe pelo menos `nome` e `duracao_min`.")
    corpo.setdefault("preco", "0.00")
    corpo.setdefault("resource_ids", [])
    return await _chamar(ctx, "POST", "/services", "agenda_admin_servico_salvar", corpo)


@mcp.tool(
    title="Criar ou alterar recurso",
    description=(
        "Recurso é a agenda propriamente dita: um profissional, uma sala, um "
        "equipamento — o que não pode ser ocupado duas vezes no mesmo horário. Sem "
        "`resource_id`, cadastra; com, altera só o que for informado. `ativo=false` "
        "tira o recurso da oferta sem apagar compromissos nem a grade dele: reativar "
        "devolve tudo. Depois de criar, defina a semana de trabalho com "
        "`agenda_admin_grade_definir` — sem grade, o recurso não oferece horário "
        "nenhum. Escopo exigido: `agenda:admin`."
    ),
)
async def agenda_admin_recurso_salvar(
    ctx: Context,
    nome: Annotated[str | None, Field(description='Ex.: "Dra. Marina", "Sala 2"')] = None,
    resource_id: Annotated[str | None, Field(description="Informe para ALTERAR; omita para criar")] = None,
    tipo: Annotated[str | None, Field(description='Livre: "profissional", "sala", "equipamento"')] = None,
    ativo: Annotated[bool | None, Field(description="false tira o recurso da oferta")] = None,
) -> dict:
    corpo = _sem_nulos(nome=nome, tipo=tipo, ativo=ativo)
    if resource_id:
        return await _chamar(
            ctx, "PATCH", f"/resources/{resource_id}", "agenda_admin_recurso_salvar", corpo
        )
    if not nome:
        raise ToolError("Para criar um recurso, informe `nome`.")
    return await _chamar(ctx, "POST", "/resources", "agenda_admin_recurso_salvar", corpo)


# ── Grade de trabalho ────────────────────────────────────────────────────────


@mcp.tool(
    title="Ver a grade semanal",
    description=(
        "As janelas de trabalho por dia da semana (0=segunda … 6=domingo), em hora "
        "local. Sem `resource_id`, devolve a grade de todos os recursos. Isto é a "
        "regra, não a disponibilidade: horário realmente livre é grade menos "
        "bloqueios, compromissos e folgas. Escopo exigido: `agenda:read`."
    ),
)
async def agenda_admin_grade_ver(
    ctx: Context,
    resource_id: Annotated[str | None, Field(description="Só a grade deste recurso")] = None,
) -> dict:
    rota = "/availability/rules" + (f"?resource_id={resource_id}" if resource_id else "")
    return {"janelas": await _chamar(ctx, "GET", rota, "agenda_admin_grade_ver")}


class Janela(BaseModel):
    """Uma faixa de trabalho num dia da semana."""

    dia_semana: Annotated[int, Field(ge=0, le=6, description="0=segunda … 6=domingo")]
    hora_inicio: Annotated[str, Field(description='Hora local, ex.: "09:00"')]
    hora_fim: Annotated[str, Field(description='Hora local, ex.: "18:00"')]


@mcp.tool(
    title="Definir a semana de trabalho",
    description=(
        "Descreva a semana do recurso **como ela deve ficar** — esta ferramenta "
        "substitui a grade inteira dele numa transação só. Não remende janela a "
        "janela: informe todas de uma vez, inclusive as que não mudaram. "
        "`janelas: []` limpa a grade (o recurso deixa de oferecer horários). "
        "Intervalo de almoço é duas janelas no mesmo dia (09:00–12:00 e 13:00–18:00). "
        "Janelas do mesmo dia não podem se sobrepor — a agenda recusa e diz quais "
        "colidiram. Escopo exigido: `agenda:admin`."
    ),
)
async def agenda_admin_grade_definir(
    ctx: Context,
    resource_id: Annotated[str, Field(description="Recurso cuja semana está sendo definida")],
    janelas: Annotated[list[Janela], Field(description="A semana completa, como deve ficar")],
) -> dict:
    return await _chamar(
        ctx,
        "PUT",
        f"/availability/rules?resource_id={resource_id}",
        "agenda_admin_grade_definir",
        {"janelas": [j.model_dump() for j in janelas]},
    )


@mcp.tool(
    title="Bloquear um período",
    description=(
        "Feriado, férias, congresso, manutenção: tira da oferta um período pontual "
        "de um recurso, sem mexer na grade semanal. Início e fim em ISO 8601 **com "
        "offset** (ex.: \"2026-09-07T00:00:00-03:00\") — data sem fuso é recusada. "
        "O `motivo` é nota interna do prestador e aparece na agenda do dia; não é "
        "mostrado a cliente. Bloquear NÃO cancela compromissos já marcados naquele "
        "período — confira antes com `agenda_admin_dia`. Escopo exigido: `agenda:admin`."
    ),
)
async def agenda_admin_bloqueio_criar(
    ctx: Context,
    resource_id: Annotated[str, Field(description="Recurso que ficará indisponível")],
    inicio: Annotated[str, Field(description="ISO 8601 com offset")],
    fim: Annotated[str, Field(description="ISO 8601 com offset")],
    motivo: Annotated[str | None, Field(description="Nota interna, ex.: 'congresso'")] = None,
) -> dict:
    return await _chamar(
        ctx,
        "POST",
        "/availability/blocks",
        "agenda_admin_bloqueio_criar",
        _sem_nulos(resource_id=resource_id, inicio=inicio, fim=fim, motivo=motivo),
    )


@mcp.tool(
    title="Remover um bloqueio",
    description=(
        "Os horários do período voltam a ser ofertados na hora. Idempotente: remover "
        "de novo devolve o mesmo resultado, com `removido: false`. Os bloqueios "
        "vigentes e futuros estão em `agenda_admin_dia`. Escopo exigido: `agenda:admin`."
    ),
)
async def agenda_admin_bloqueio_remover(
    ctx: Context,
    block_id: Annotated[str, Field(description="Id do bloqueio")],
) -> dict:
    return await _chamar(
        ctx, "DELETE", f"/availability/blocks/{block_id}", "agenda_admin_bloqueio_remover"
    )


# ── A operação ───────────────────────────────────────────────────────────────


@mcp.tool(
    title="Como está o dia",
    description=(
        "A agenda de um dia, já narrada: compromissos na ordem, com status, cliente e "
        "risco de falta, mais os bloqueios vigentes. Use para responder \"como está "
        "minha quinta?\". **Não** use para procurar horário livre — para isso a "
        "pergunta é outra e a resposta vem do motor de slots. Traz nome e contato de "
        "todos os clientes do dia, por isso exige `agenda:operacao`."
    ),
)
async def agenda_admin_dia(
    ctx: Context,
    data: Annotated[str, Field(description='Data no formato AAAA-MM-DD, ex.: "2026-09-03"')],
) -> dict:
    dia = await _chamar(ctx, "GET", f"/agenda/day?date={data}", "agenda_admin_dia")
    bloqueios = await _chamar(ctx, "GET", "/availability/blocks", "agenda_admin_dia")
    return {**dia, "bloqueios_vigentes": bloqueios}


@mcp.tool(
    title="Fila de espera",
    description=(
        "Quem está esperando vaga, na ordem de chegada, com a janela desejada e a "
        "posição por serviço. Entradas com status `ofertado` já receberam um horário "
        "pelo canal e têm prazo para aceitar — **não há reserva**: o horário segue "
        "livre e quem confirmar primeiro leva. Traz nome e contato de todo mundo que "
        "espera, por isso exige `agenda:operacao`."
    ),
)
async def agenda_admin_fila(
    ctx: Context,
    service_id: Annotated[str | None, Field(description="Só a fila deste serviço")] = None,
    incluir_encerrados: Annotated[
        bool, Field(description="Também mostra aceito/expirado/cancelado")
    ] = False,
) -> dict:
    filtros = []
    if service_id:
        filtros.append(f"service_id={service_id}")
    if incluir_encerrados:
        filtros.append("incluir_encerrados=true")
    rota = "/waitlist" + ("?" + "&".join(filtros) if filtros else "")
    return {"fila": await _chamar(ctx, "GET", rota, "agenda_admin_fila")}


# ── A ação irreversível ──────────────────────────────────────────────────────


class ConfirmacaoDeCancelamento(BaseModel):
    """Resposta humana à prévia do cancelamento."""

    confirmar: Annotated[
        bool, Field(description="Sim, cancelar este compromisso e liberar o horário")
    ]


@mcp.tool(
    title="Cancelar um compromisso",
    description=(
        "Cancela e devolve o horário à grade **na hora** — se houver fila de espera, "
        "a próxima pessoa é avisada em seguida. Por isso não tem volta: o horário "
        "pode ser tomado por outro cliente antes de você mudar de ideia.\n\n"
        "A confirmação humana é obrigatória e não é opcional para o agente. A "
        "primeira chamada devolve a prévia (cliente, horário) e pede o OK; só depois "
        "o cancelamento acontece. Se o seu cliente MCP não souber pedir confirmação, "
        "a ferramenta devolve a prévia e um `confirmation_token` — mostre a prévia à "
        "pessoa, e só com o sim dela chame de novo passando o token.\n\n"
        "Escopo exigido: `agenda:cancel`. Um agente de atendimento não tem esse "
        "escopo: cancelamento pedido por cliente no WhatsApp vai para um humano."
    ),
)
async def agenda_admin_cancelar(
    ctx: Context,
    appointment_id: Annotated[str, Field(description="Id do compromisso (veja `agenda_admin_dia`)")],
    motivo: Annotated[str | None, Field(description="Fica no histórico do compromisso")] = None,
    confirmation_token: Annotated[
        str | None,
        Field(description="Só na segunda chamada, quando a confirmação veio por fora"),
    ] = None,
) -> dict:
    rota = f"/appointments/{appointment_id}/cancel"
    corpo = _sem_nulos(motivo=motivo, confirmation_token=confirmation_token)
    autorizacao = _autorizacao(ctx)
    await sessao.quem_e(autorizacao, tool="agenda_admin_cancelar")

    try:
        cancelado = await agenda.chamar(
            "POST", rota, autorizacao, tool="agenda_admin_cancelar", corpo=corpo
        )
        return {"cancelado": True, "compromisso": cancelado}
    except AgendaRecusou as e:
        if e.code != "CONFIRMACAO_NECESSARIA":
            raise ToolError(e.para_o_modelo()) from e
        previa = e.extra.get("previa", {})
        token = e.extra.get("confirmation_token")
    except AgendaIndisponivel as e:
        raise ToolError(f"{e} Nada foi alterado.") from e

    pergunta = (
        f"Cancelar o horário de {previa.get('cliente', 'este cliente')} em "
        f"{previa.get('horario', '—')}? O horário volta para a grade imediatamente e "
        "pode ser ocupado por outra pessoa — não dá para desfazer."
    )

    if not _cliente_sabe_confirmar(ctx):
        # Fallback do `00` §5.7: o cliente MCP não implementa elicitation, então
        # a confirmação sai daqui e volta na segunda chamada. O que NÃO acontece
        # é o agente confirmar sozinho — o token é inútil sem alguém que o repasse.
        return {
            "cancelado": False,
            "confirmacao_necessaria": True,
            "previa": previa,
            "confirmation_token": token,
            "como_prosseguir": (
                "Mostre a prévia à pessoa responsável. Com o sim dela, chame esta "
                "ferramenta de novo com o mesmo appointment_id e o confirmation_token "
                "acima (ele expira em 5 minutos)."
            ),
        }

    resposta = await ctx.elicit(pergunta, ConfirmacaoDeCancelamento)
    if resposta.action != "accept" or not resposta.data.confirmar:
        return {
            "cancelado": False,
            "motivo": "A confirmação foi recusada — nada mudou.",
            "previa": previa,
        }

    try:
        cancelado = await agenda.chamar(
            "POST",
            rota,
            autorizacao,
            tool="agenda_admin_cancelar",
            corpo={**corpo, "confirmation_token": token},
        )
    except AgendaRecusou as e:
        raise ToolError(e.para_o_modelo()) from e
    return {"cancelado": True, "compromisso": cancelado}


def _cliente_sabe_confirmar(ctx: Context) -> bool:
    """Elicitation é capacidade negociada no handshake — nem todo cliente MCP a
    tem. Perguntar antes evita um erro de protocolo no lugar de uma pergunta."""
    return getattr(ctx.client_capabilities, "elicitation", None) is not None


# ── Integrações ──────────────────────────────────────────────────────────────


@mcp.tool(
    title="Listar credenciais de integração",
    description=(
        "Quem alcança esta agenda por integração, com que autoridade e quando usou "
        "pela última vez. **Somente leitura, e de propósito**: emitir e revogar "
        "credencial não é operação de agente. Uma ferramenta que distribui autoridade "
        "seria a peça que transforma um token vazado em acesso permanente — isso se "
        "faz na tela de Integrações ou no servidor. O token nunca aparece aqui: o "
        "banco guarda só um resumo criptográfico. Escopo exigido: `credenciais:admin`, "
        "que nenhum papel de agente traz por padrão."
    ),
)
async def agenda_admin_credenciais_listar(ctx: Context) -> dict:
    return {"credenciais": await _chamar(ctx, "GET", "/credenciais", "agenda_admin_credenciais_listar")}


# ── Prompts (§14.3) ──────────────────────────────────────────────────────────
#
# Prompt aqui é roteiro, não automação: ele diz ao modelo em que ordem chamar
# as tools e o que reportar. Fica no conector administrativo porque os três do
# PRD são perguntas de quem opera a agenda — quem atende um cliente vê uma
# agenda de uma pessoa só, e nenhuma dessas perguntas faz sentido lá.


@mcp.prompt(
    title="Como está o dia",
    description="Lê a agenda de um dia e destaca conflitos, faltas prováveis e buracos.",
)
def agenda_do_dia(data: str) -> str:
    return (
        f"Use `agenda_admin_dia` para {data} e me devolva, nesta ordem:\n"
        "1. quantos compromissos e quanto tempo somam;\n"
        "2. quem está com risco de falta alto ou médio — nomeie e diga o horário;\n"
        "3. os buracos entre um atendimento e outro, com duração;\n"
        "4. bloqueios vigentes que expliquem esses buracos.\n\n"
        "Fale em português claro, horários por extenso (use o `label_humano` que vier "
        "na resposta). Não invente números: se algo não veio na resposta, diga que não "
        "veio."
    )


@mcp.prompt(
    title="Remarcar a semana",
    description="Dado um bloqueio novo (férias, imprevisto), lista os afetados e propõe realocação.",
)
def remarcar_semana(de: str, ate: str, motivo: str = "imprevisto") -> str:
    return (
        f"Preciso bloquear de {de} a {ate} ({motivo}).\n\n"
        "Antes de mudar qualquer coisa:\n"
        "1. use `agenda_admin_dia` em cada dia do período e liste quem está marcado;\n"
        "2. para cada pessoa, use `agenda_admin_grade_ver` e proponha 2 horários "
        "alternativos próximos, fora do período bloqueado;\n"
        "3. me mostre a lista completa — pessoa, horário atual, alternativas — e "
        "**pare aí**.\n\n"
        "Não crie o bloqueio nem remarque ninguém sem meu OK explícito: remarcar "
        "compromisso de cliente é conversa que alguém precisa ter, não efeito colateral "
        "de um bloqueio."
    )


@mcp.prompt(
    title="Confirmar pendentes",
    description="Lista compromissos das próximas 24h sem confirmação e prepara as mensagens.",
)
def confirmar_pendentes(data: str) -> str:
    return (
        f"Use `agenda_admin_dia` para {data} e separe os compromissos que ainda estão "
        "como `agendado` (ou seja, o cliente não confirmou).\n\n"
        "Para cada um, escreva a mensagem que eu mandaria — curta, cordial, com a data "
        "por extenso e uma pergunta fechada ('confirma?'). Destaque quem tem risco de "
        "falta alto.\n\n"
        "Só escreva os textos: quem dispara mensagem ativa é a régua de lembretes do "
        "produto, por template aprovado — não o agente, e não por aqui."
    )
