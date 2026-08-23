# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Cancelar: a ação que este conector existe para NÃO executar sozinho.

Duas camadas, e as duas importam. A credencial de atendimento não tem
`agenda:cancel` — a agenda recusa, e o conector traduz a recusa em
"encaminhe a um humano" em vez de um 403 que o modelo tentaria contornar.
Onde há autoridade, a confirmação humana ainda é obrigatória.
"""

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from app import servidor

PREVIA = {"compromisso": "ap1", "cliente": "Ana Prado", "horario": "quinta, 11 de março, 15h"}


def _pede_confirmacao(agenda_falsa):
    agenda_falsa.responder(
        "POST",
        "/appointments/ap1/cancel",
        409,
        {
            "code": "CONFIRMACAO_NECESSARIA",
            "message": "Cancelamento é irreversível e exige confirmação humana.",
            "hint": "Mostre a prévia ao humano e repita com o confirmation_token.",
            "previa": PREVIA,
            "confirmation_token": "cancel.ap1.123.abc",
        },
    )


async def test_atendimento_nao_cancela_e_a_conversa_vai_para_humano(agenda_falsa, ctx):
    """O aceite do §14.4: credencial com read+write não cancela. O texto que
    volta diz o que fazer — falar com uma pessoa —, não como tentar de novo."""
    agenda_falsa.responder(
        "POST",
        "/appointments/ap1/cancel",
        403,
        {
            "code": "ESCOPO_INSUFICIENTE",
            "message": "A credencial não tem o escopo 'agenda:cancel'.",
            "hint": "Peça uma credencial com o escopo necessário.",
        },
    )
    with pytest.raises(ToolError) as e:
        await servidor.agenda_cancelar(ctx, appointment_id="ap1")
    texto = str(e.value)
    assert "atendente" in texto
    assert "não tente por outro caminho" in texto


async def test_sem_elicitation_devolve_previa_e_token(agenda_falsa, ctx):
    """Cliente MCP que não sabe perguntar não vira permissão para o agente
    decidir: o token é inútil sem alguém que o repasse."""
    _pede_confirmacao(agenda_falsa)
    resposta = await servidor.agenda_cancelar(ctx, appointment_id="ap1")

    assert resposta["cancelado"] is False
    assert resposta["previa"] == PREVIA
    assert resposta["confirmation_token"] == "cancel.ap1.123.abc"
    assert "pessoa responsável" in resposta["como_prosseguir"]


async def test_com_elicitation_a_pessoa_confirma_e_so_entao_cancela(agenda_falsa, ctx):
    _pede_confirmacao(agenda_falsa)
    agenda_falsa.responder(
        "POST", "/appointments/ap1/cancel", 200, {"id": "ap1", "status": "cancelado"}
    )
    ctx.sabe_confirmar = True
    ctx.resposta_da_pessoa = type(
        "R", (), {"action": "accept", "data": type("D", (), {"confirmar": True})()}
    )()

    resposta = await servidor.agenda_cancelar(ctx, appointment_id="ap1")
    assert resposta["cancelado"] is True
    assert "não dá para desfazer" in ctx.perguntas[0]
    # a segunda chamada leva o token que a primeira devolveu
    corpo_da_segunda = [c for c in agenda_falsa.chamadas if c[0] == "POST"][-1]
    assert corpo_da_segunda[1] == "/appointments/ap1/cancel"


async def test_pessoa_recusando_nao_cancela_nada(agenda_falsa, ctx):
    _pede_confirmacao(agenda_falsa)
    ctx.sabe_confirmar = True
    ctx.resposta_da_pessoa = type(
        "R", (), {"action": "accept", "data": type("D", (), {"confirmar": False})()}
    )()

    resposta = await servidor.agenda_cancelar(ctx, appointment_id="ap1")
    assert resposta["cancelado"] is False
    assert "nada mudou" in resposta["motivo"]
