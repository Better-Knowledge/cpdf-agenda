"""RF-17 — o OpenAPI é o contrato executável do módulo.

Aqui vive o que torna o `/docs` auto-suficiente para um agente (ou aluno):
o schema único de erro `{code, message, hint, retryable}`, o catálogo de
exemplos de cada código e os helpers que cada rota usa para declarar seus
erros (`respostas`) e seu escopo/idempotência (`operacao`).
"""

from typing import Any

from pydantic import BaseModel, Field

# ── Schema único de erro (convenção do programa) ─────────────────────────────


class Alternativa(BaseModel):
    inicio: str = Field(description="ISO 8601 com offset")
    label_humano: str


class ErroOut(BaseModel):
    """Todo erro da API tem este formato. O `hint` é escrito para o agente
    agir — quando possível, a saída já vem no payload (ex.: alternativas)."""

    code: str = Field(description="Código estável, ex.: SLOT_INDISPONIVEL")
    message: str = Field(description="O que aconteceu, em uma frase")
    hint: str = Field(description="O próximo passo, escrito para o agente executar")
    retryable: bool = Field(description="true = repetir a mesma chamada pode funcionar")
    alternativas: list[Alternativa] | None = Field(
        default=None,
        description="Só em SLOT_INDISPONIVEL: os 3 horários livres mais próximos",
    )
    previa: dict[str, Any] | None = Field(
        default=None,
        description="Só em CONFIRMACAO_NECESSARIA: o que será feito, para mostrar ao humano",
    )
    confirmation_token: str | None = Field(
        default=None,
        description="Só em CONFIRMACAO_NECESSARIA: repita a chamada com ele após o OK humano (expira em 5 min)",
    )


# ── Catálogo de erros: code → (status, resumo, exemplo) ──────────────────────

_HORARIO = "quinta, 27 de agosto, 15h30"

CATALOGO: dict[str, tuple[int, str, dict[str, Any]]] = {
    "NAO_AUTENTICADO": (
        401,
        "Credencial ausente ou inválida",
        {
            "code": "NAO_AUTENTICADO",
            "message": "Credencial ausente ou inválida: nenhum header de credencial presente",
            "hint": (
                "Envie `Authorization: Bearer agk_…` (credencial de agente), `ats_…` "
                "(sessão de atendimento) ou o JWT do Supabase."
            ),
            "retryable": False,
        },
    ),
    "ESCOPO_INSUFICIENTE": (
        403,
        "A credencial não tem o escopo exigido",
        {
            "code": "ESCOPO_INSUFICIENTE",
            "message": "A credencial não tem o escopo 'agenda:cancel'.",
            "hint": "Peça uma credencial com o escopo necessário — cancelamento exige agenda:cancel.",
            "retryable": False,
        },
    ),
    "NAO_ENCONTRADO": (
        404,
        "Id não existe nesta organização",
        {
            "code": "NAO_ENCONTRADO",
            "message": "Serviço 6f1e…9c02 não existe nesta organização.",
            "hint": "Confira o id — liste o recurso correspondente para obter ids válidos.",
            "retryable": False,
        },
    ),
    "PAYLOAD_INVALIDO": (
        422,
        "Corpo ou parâmetros não passaram na validação",
        {
            "code": "PAYLOAD_INVALIDO",
            "message": "Payload inválido: body.cliente_telefone: String should have at least 8 characters",
            "hint": "Corrija os campos apontados e repita a chamada com os mesmos dados.",
            "retryable": False,
        },
    ),
    "DATA_SEM_FUSO": (
        400,
        "Horário sem offset de fuso",
        {
            "code": "DATA_SEM_FUSO",
            "message": "'inicio' veio sem offset de fuso horário.",
            "hint": "Envie ISO 8601 com offset explícito, ex.: 2026-08-27T15:30:00-03:00.",
            "retryable": False,
        },
    ),
    "ESCOPO_NAO_DELEGAVEL": (
        403,
        "Este escopo não pode ser concedido por rota",
        {
            "code": "ESCOPO_NAO_DELEGAVEL",
            "message": "`credenciais:admin` não pode ser concedido por esta rota.",
            "hint": (
                "Uma credencial que emite credenciais sobrevive à própria revogação. "
                "Se realmente for necessário, emita pelo servidor: `make credencial`."
            ),
            "retryable": False,
        },
    ),
    "SESSAO_INVALIDA": (
        401,
        "Token de sessão de atendimento inválido ou expirado",
        {
            "code": "SESSAO_INVALIDA",
            "message": "Token de sessão de atendimento inválido: expirado",
            "hint": (
                "O token é cunhado pelo canal a cada mensagem do cliente e vale 30 "
                "minutos. Aguarde a próxima mensagem em vez de reaproveitar o antigo."
            ),
            "retryable": False,
        },
    ),
    "TITULAR_DIVERGENTE": (
        403,
        "A sessão de atendimento fala por outro cliente",
        {
            "code": "TITULAR_DIVERGENTE",
            "message": "Esta sessão de atendimento não fala pelo cliente informado.",
            "hint": (
                "O token de sessão é cunhado pelo canal para o cliente que escreveu. "
                "Omita `cliente_telefone` ou use o endereço da conversa."
            ),
            "retryable": False,
        },
    ),
    "OAUTH_ESTADO_INVALIDO": (
        400,
        "O state do OAuth não confere",
        {
            "code": "OAUTH_ESTADO_INVALIDO",
            "message": "O state do OAuth é inválido ou expirou.",
            "hint": "Recomece a conexão pela tela de Integrações — o link vale 10 minutos.",
            "retryable": False,
        },
    ),
    "GOOGLE_NAO_CONFIGURADO": (
        409,
        "Este servidor não tem app OAuth do Google",
        {
            "code": "GOOGLE_NAO_CONFIGURADO",
            "message": "Este servidor não tem app OAuth do Google configurado.",
            "hint": (
                "Configure GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET no .env do VPS. "
                "Sem isso, use o feed .ics (POST /ics/tokens), que não exige OAuth."
            ),
            "retryable": False,
        },
    ),
    "MUITAS_REQUISICOES": (
        429,
        "Limite de requisições por IP na página pública",
        {
            "code": "MUITAS_REQUISICOES",
            "message": "Muitas requisições deste endereço em pouco tempo.",
            "hint": "Aguarde 40s e tente de novo.",
            "retryable": True,
        },
    ),
    "DATA_NO_PASSADO": (
        400,
        "O horário escolhido já passou",
        {
            "code": "DATA_NO_PASSADO",
            "message": "O horário escolhido já passou.",
            "hint": "Recarregue a página e escolha um horário na lista de livres.",
            "retryable": False,
        },
    ),
    "SLUG_INDISPONIVEL": (
        409,
        "O endereço do link já está em uso",
        {
            "code": "SLUG_INDISPONIVEL",
            "message": "Não foi possível reservar um endereço para este link.",
            "hint": "Envie um `slug` diferente no corpo da chamada.",
            "retryable": False,
        },
    ),
    "ASSINATURA_INVALIDA": (
        401,
        "A assinatura do webhook não confere",
        {
            "code": "ASSINATURA_INVALIDA",
            "message": "A assinatura deste webhook não confere com nenhuma integração ativa.",
            "hint": "Confira a signing key em PUT /integracoes/calendly e o relógio do servidor.",
            "retryable": False,
        },
    ),
    "LINK_INATIVO": (
        409,
        "O link de auto-agendamento está desativado",
        {
            "code": "LINK_INATIVO",
            "message": "Este link de agendamento está desativado no momento.",
            "hint": "Fale com o prestador pelo WhatsApp — a conversa continua funcionando.",
            "retryable": False,
        },
    ),
    "PERIODO_INVALIDO": (
        400,
        "Fim antes do início",
        {
            "code": "PERIODO_INVALIDO",
            "message": "O fim do bloqueio precisa ser depois do início.",
            "hint": "Inverta os valores ou confira o offset de fuso.",
            "retryable": False,
        },
    ),
    "CURSOR_INVALIDO": (
        400,
        "Cursor de paginação não reconhecido",
        {
            "code": "CURSOR_INVALIDO",
            "message": "O cursor de paginação não foi reconhecido.",
            "hint": "Use exatamente o next_cursor devolvido pela página anterior.",
            "retryable": False,
        },
    ),
    "SLOT_INDISPONIVEL": (
        409,
        "Horário ocupado — alternativas já no payload",
        {
            "code": "SLOT_INDISPONIVEL",
            "message": "O horário pedido já está ocupado ou fora da grade.",
            "hint": f"Ofereça estas alternativas ao cliente: {_HORARIO} · quinta, 27 de agosto, 16h30 · sexta, 28 de agosto, 9h.",
            "retryable": False,
            "alternativas": [
                {"inicio": "2026-08-27T15:30:00-03:00", "label_humano": _HORARIO},
                {"inicio": "2026-08-27T16:30:00-03:00", "label_humano": "quinta, 27 de agosto, 16h30"},
                {"inicio": "2026-08-28T09:00:00-03:00", "label_humano": "sexta, 28 de agosto, 9h"},
            ],
        },
    ),
    "CONFIRMACAO_NECESSARIA": (
        409,
        "Ação irreversível: confirme com o humano e repita com o token",
        {
            "code": "CONFIRMACAO_NECESSARIA",
            "message": "Cancelamento é irreversível e exige confirmação humana.",
            "hint": "Mostre a prévia ao humano e, com o OK, repita esta chamada com o confirmation_token do payload.",
            "retryable": False,
            "previa": {
                "compromisso": "0b6ff65e-…",
                "cliente": "Paula Andrade",
                "horario": _HORARIO,
            },
            "confirmation_token": "cancel.0b6ff65e….1756312200.f3ab…",
        },
    ),
    "CONFIRMACAO_INVALIDA": (
        409,
        "confirmation_token não vale para esta ação",
        {
            "code": "CONFIRMACAO_INVALIDA",
            "message": "confirmation_token inválido para esta ação.",
            "hint": "Refaça a chamada sem token para receber uma nova prévia e um token novo.",
            "retryable": False,
        },
    ),
    "CONFIRMACAO_EXPIRADA": (
        409,
        "confirmation_token passou dos 5 minutos",
        {
            "code": "CONFIRMACAO_EXPIRADA",
            "message": "O confirmation_token expirou (validade de 5 minutos).",
            "hint": "Refaça a chamada sem token, confirme com o humano e use o token novo.",
            "retryable": False,
        },
    ),
    "STATUS_INCOMPATIVEL": (
        409,
        "O status atual não permite a ação",
        {
            "code": "STATUS_INCOMPATIVEL",
            "message": "Compromisso está 'cancelado' — não dá para reagendar.",
            "hint": "Crie um novo agendamento com POST /appointments.",
            "retryable": False,
        },
    ),
    "OFERTA_EXPIRADA": (
        409,
        "A janela para aceitar a oferta da fila passou",
        {
            "code": "OFERTA_EXPIRADA",
            "message": "A janela para aceitar esta oferta já passou.",
            "hint": (
                "O horário foi oferecido a quem estava atrás na fila. Entre de novo "
                "com POST /waitlist ou consulte GET /slots para agendar direto."
            ),
            "retryable": False,
        },
    ),
    "CANAL_NAO_CONFIGURADO": (
        409,
        "A organização ainda não configurou o canal de WhatsApp",
        {
            "code": "CANAL_NAO_CONFIGURADO",
            "message": "A organização não tem canal de WhatsApp configurado.",
            "hint": "Configure driver, número dedicado e credenciais em POST /canal/config.",
            "retryable": False,
        },
    ),
    "NUMERO_PESSOAL_RECUSADO": (
        400,
        "O canal exige número dedicado — nunca o pessoal",
        {
            "code": "NUMERO_PESSOAL_RECUSADO",
            "message": "O canal exige um número de WhatsApp dedicado à organização.",
            "hint": (
                "Não use o número pessoal: drivers não-oficiais podem ser banidos pelo "
                "WhatsApp. Provisione um número próprio e confirme com "
                "confirmo_numero_dedicado=true."
            ),
            "retryable": False,
        },
    ),
    "FALHA_NO_DRIVER": (
        502,
        "O driver de WhatsApp não respondeu à operação",
        {
            "code": "FALHA_NO_DRIVER",
            "message": "O driver evolution não respondeu à operação de conexão.",
            "hint": "evolution inacessível: timeout — verifique o servidor do driver.",
            "retryable": True,
        },
    ),
    "CANAL_INDISPONIVEL": (
        502,
        "O canal-service não respondeu",
        {
            "code": "CANAL_INDISPONIVEL",
            "message": "O canal de WhatsApp não respondeu.",
            "hint": "Tente de novo em instantes — a operação é segura para repetir.",
            "retryable": True,
        },
    ),
}

_DESCRICAO_STATUS = {
    400: "Pedido malformado",
    429: "Excesso de requisições — o hint diz quanto esperar",
    401: "Não autenticado",
    403: "Escopo insuficiente",
    404: "Não encontrado nesta organização",
    409: "Conflito — o hint diz como resolver",
    422: "Validação falhou",
    502: "Dependência não respondeu — retry é seguro",
}

# Todo endpoint autenticado pode devolver estes três.
# SESSAO_INVALIDA é de base porque um token de atendimento expirado derruba
# QUALQUER rota — a sessão vale 30 min e a conversa costuma durar mais.
_BASE = ("NAO_AUTENTICADO", "SESSAO_INVALIDA", "ESCOPO_INSUFICIENTE", "PAYLOAD_INVALIDO")


def respostas(*codes: str) -> dict[int | str, dict[str, Any]]:
    """Monta o `responses=` de uma rota a partir do catálogo de erros.

    Os erros de base (401/403/422) entram sempre; passe só os específicos
    da rota (ex.: "SLOT_INDISPONIVEL"). Códigos com o mesmo status HTTP
    viram exemplos nomeados na mesma resposta.
    """
    saida: dict[int | str, dict[str, Any]] = {}
    for code in (*_BASE, *codes):
        status, resumo, exemplo = CATALOGO[code]
        resposta = saida.setdefault(
            status,
            {
                "model": ErroOut,
                "description": _DESCRICAO_STATUS[status],
                "content": {"application/json": {"examples": {}}},
            },
        )
        resposta["content"]["application/json"]["examples"][code] = {
            "summary": resumo,
            "value": exemplo,
        }
    return saida


def respostas_publicas(*codes: str) -> dict[int | str, dict[str, Any]]:
    """Como `respostas`, mas sem os erros de base — para as rotas sem credencial.

    Três existem: `/health`, o feed `.ics` (o segredo é o token na URL) e o
    callback do OAuth (quem chama é o navegador redirecionado pelo Google).
    Documentar 401/403 nelas seria mentir sobre o contrato — mas 422 vale
    para todas, porque o handler de validação é do app inteiro.
    """
    saida: dict[int | str, dict[str, Any]] = {}
    for code in ("PAYLOAD_INVALIDO", *codes):
        status, resumo, exemplo = CATALOGO[code]
        resposta = saida.setdefault(
            status,
            {
                "model": ErroOut,
                "description": _DESCRICAO_STATUS[status],
                "content": {"application/json": {"examples": {}}},
            },
        )
        resposta["content"]["application/json"]["examples"][code] = {
            "summary": resumo,
            "value": exemplo,
        }
    return saida


# ── Escopo e idempotência declarados por rota (viram doc no /docs) ───────────

_PARAM_IDEMPOTENCY = {
    "name": "Idempotency-Key",
    "in": "header",
    "required": False,
    "schema": {"type": "string", "format": "uuid"},
    "description": (
        "Repetir a chamada com a mesma chave devolve a resposta original sem "
        "duplicar efeito. Obrigatório para agentes; use um UUID novo por intenção."
    ),
}


def operacao(escopo: str, *, idempotente: bool = False) -> dict[str, Any]:
    """`openapi_extra` de uma rota: escopo exigido e header de idempotência.

    O `x-escopo-requerido` é lido pelo main.openapi() para estampar o escopo
    na descrição — e será a fonte dos escopos das tools do agenda-mcp (§14).
    """
    extra: dict[str, Any] = {"x-escopo-requerido": escopo}
    if idempotente:
        extra["parameters"] = [_PARAM_IDEMPOTENCY]
    return extra
