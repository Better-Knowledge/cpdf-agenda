"""Cancelar é irreversível — e o agente não confirma sozinho (`00` §5.7).

O horário volta para a grade na hora e a fila de espera é avisada em seguida:
quando o humano muda de ideia, o horário já pode ser de outra pessoa. Por isso
o gradiente de risco do programa põe o cancelamento no extremo em que a
decisão nunca é do modelo.
"""

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from app import servidor

from .conftest import ContextoFalso

PEDE_CONFIRMACAO = (
    409,
    {
        "code": "CONFIRMACAO_NECESSARIA",
        "message": "Cancelamento é irreversível e exige confirmação humana.",
        "hint": "Mostre a prévia ao humano e repita com o confirmation_token.",
        "retryable": False,
        "previa": {"compromisso": "ap-1", "cliente": "Paula Andrade", "horario": "quinta, 27 de agosto, 15h30"},
        "confirmation_token": "tok-123",
    },
)
CANCELADO = {"id": "ap-1", "status": "cancelado", "label_humano": "quinta, 27 de agosto, 15h30"}


class Aceitou:
    action = "accept"
    data = type("D", (), {"confirmar": True})()


class Recusou:
    action = "decline"
    data = None


class AceitouMasDisseNao:
    action = "accept"
    data = type("D", (), {"confirmar": False})()


def _armar(agenda_falsa):
    agenda_falsa.responder("POST", "/appointments/ap-1/cancel", *PEDE_CONFIRMACAO)


async def test_sem_confirmacao_nada_e_cancelado(agenda_falsa):
    """O cliente MCP não sabe perguntar: a tool devolve a prévia e o token, e
    para por aí. O token é inútil sem alguém que o repasse — que é o ponto."""
    _armar(agenda_falsa)
    ctx = ContextoFalso(sabe_confirmar=False)
    resultado = await servidor.agenda_admin_cancelar(ctx, appointment_id="ap-1")

    assert resultado["cancelado"] is False
    assert resultado["confirmacao_necessaria"] is True
    assert resultado["previa"]["cliente"] == "Paula Andrade"
    assert resultado["confirmation_token"] == "tok-123"
    assert "Mostre a prévia" in resultado["como_prosseguir"]
    assert len([c for c in agenda_falsa.chamadas if c[0] == "POST"]) == 1


async def test_o_humano_confirma_e_o_cancelamento_acontece(agenda_falsa):
    _armar(agenda_falsa)
    agenda_falsa.responder("POST", "/appointments/ap-1/cancel", 200, CANCELADO)
    ctx = ContextoFalso(sabe_confirmar=True, resposta_da_pessoa=Aceitou())

    resultado = await servidor.agenda_admin_cancelar(ctx, appointment_id="ap-1", motivo="pedido")

    assert resultado["cancelado"] is True
    assert resultado["compromisso"]["status"] == "cancelado"
    # A pergunta é feita em português de gente, com o nome e o horário na frente
    assert "Paula Andrade" in ctx.perguntas[0]
    assert "não dá para desfazer" in ctx.perguntas[0]


async def test_o_token_da_previa_e_o_que_volta_na_segunda_chamada(agenda_falsa):
    """Sem isto, a segunda chamada seria idêntica à primeira e o cancelamento
    entraria em laço: pedir confirmação, receber sim, pedir de novo."""
    _armar(agenda_falsa)
    agenda_falsa.responder("POST", "/appointments/ap-1/cancel", 200, CANCELADO)
    corpos = []

    from app import agenda as cliente_agenda

    original = cliente_agenda.chamar

    async def espiar(metodo, rota, autorizacao, *, tool, corpo=None):
        if rota.endswith("/cancel"):
            corpos.append(corpo)
        return await original(metodo, rota, autorizacao, tool=tool, corpo=corpo)

    import pytest as _pytest  # noqa: F401

    cliente_agenda.chamar = espiar
    try:
        await servidor.agenda_admin_cancelar(
            ContextoFalso(sabe_confirmar=True, resposta_da_pessoa=Aceitou()), appointment_id="ap-1"
        )
    finally:
        cliente_agenda.chamar = original

    assert "confirmation_token" not in corpos[0]
    assert corpos[1]["confirmation_token"] == "tok-123"


@pytest.mark.parametrize("resposta", [Recusou(), AceitouMasDisseNao()])
async def test_recusa_humana_para_o_cancelamento(agenda_falsa, resposta):
    _armar(agenda_falsa)
    ctx = ContextoFalso(sabe_confirmar=True, resposta_da_pessoa=resposta)
    resultado = await servidor.agenda_admin_cancelar(ctx, appointment_id="ap-1")

    assert resultado["cancelado"] is False
    assert "nada mudou" in resultado["motivo"]
    # uma só chamada de cancelamento: a que voltou pedindo confirmação
    assert len([c for c in agenda_falsa.chamadas if c[0] == "POST"]) == 1


async def test_token_vindo_de_fora_cancela_direto(agenda_falsa):
    """O caminho da segunda chamada: a pessoa já viu a prévia e disse sim."""
    agenda_falsa.responder("POST", "/appointments/ap-1/cancel", 200, CANCELADO)
    ctx = ContextoFalso()
    resultado = await servidor.agenda_admin_cancelar(
        ctx, appointment_id="ap-1", confirmation_token="tok-123"
    )
    assert resultado["cancelado"] is True
    assert ctx.perguntas == []


async def test_token_expirado_nao_vira_confirmacao_silenciosa(agenda_falsa):
    agenda_falsa.responder(
        "POST",
        "/appointments/ap-1/cancel",
        409,
        {
            "code": "CONFIRMACAO_EXPIRADA",
            "message": "O confirmation_token expirou (validade de 5 minutos).",
            "hint": "Refaça a chamada sem token, confirme com o humano e use o token novo.",
            "retryable": False,
        },
    )
    with pytest.raises(ToolError) as erro:
        await servidor.agenda_admin_cancelar(
            ContextoFalso(), appointment_id="ap-1", confirmation_token="velho"
        )
    assert "expirou" in str(erro.value)


async def test_sem_escopo_de_cancelamento_a_recusa_e_da_agenda(agenda_falsa):
    """O conector não confere escopo — quem recusa é a agenda, com o mesmo 403
    que daria a um curl. Duas fontes de verdade sobre autoridade seria uma a
    mais, e a que diverge é sempre a que ninguém olha."""
    agenda_falsa.responder(
        "POST",
        "/appointments/ap-1/cancel",
        403,
        {
            "code": "ESCOPO_INSUFICIENTE",
            "message": "A credencial não tem o escopo 'agenda:cancel'.",
            "hint": "Esta credencial tem ['agenda:read', 'agenda:write'].",
            "retryable": False,
        },
    )
    ctx = ContextoFalso(sabe_confirmar=True, resposta_da_pessoa=Aceitou())
    with pytest.raises(ToolError) as erro:
        await servidor.agenda_admin_cancelar(ctx, appointment_id="ap-1")
    assert "agenda:cancel" in str(erro.value)
    assert ctx.perguntas == [], "não faz sentido perguntar sobre algo que seria recusado"
