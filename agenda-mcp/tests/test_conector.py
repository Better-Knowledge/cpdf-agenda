# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""O conector de atendimento: o que ele repassa, e o que ele se recusa a decidir.

O que se testa aqui é o conector — rotas montadas, headers repassados,
tradução da recusa. O que a agenda faz com aquilo já é testado no
`agenda-service`; repetir criaria duas verdades sobre a mesma regra.
"""

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from app import servidor
from app.config import Settings

from .conftest import BEARER


async def test_o_conector_nao_tem_credencial_propria():
    """A regra inegociável do §14.5, que vale igual aqui: uma chave de serviço
    neste `.env` recriaria o deputado confuso que o RF-18 eliminou. O teste
    falha se alguém adicionar qualquer campo com cara de segredo."""
    suspeitos = [
        campo
        for campo in Settings.model_fields
        if any(p in campo for p in ("key", "token", "secret", "chave", "segredo", "credencial"))
    ]
    assert suspeitos == []


async def test_a_credencial_da_conexao_e_repassada_intacta(agenda_falsa, ctx):
    agenda_falsa.padrao = {"items": []}
    await servidor.agenda_listar_servicos(ctx)

    (_, _, cabecalhos) = agenda_falsa.chamadas[-1]
    assert cabecalhos["authorization"] == BEARER
    assert cabecalhos["x-mcp-server"] == "agenda"
    assert cabecalhos["x-mcp-tool"] == "agenda_listar_servicos"


async def test_sem_credencial_a_mensagem_ensina_o_caminho(agenda_falsa, ctx):
    ctx.autorizacao = None
    with pytest.raises(ToolError) as e:
        await servidor.agenda_listar_servicos(ctx)
    assert "ats_" in str(e.value)  # diz qual token o canal cunha


async def test_consultar_slots_aceita_portugues(agenda_falsa, ctx):
    agenda_falsa.padrao = []
    resposta = await servidor.agenda_consultar_slots(ctx, service_id="s1", quando="amanhã de tarde")

    (_, rota, _) = agenda_falsa.chamadas[-1]
    assert "/slots?service_id=s1" in rota
    assert "T12:00" in rota and "T18:00" in rota  # a tarde, em hora de parede
    assert "-03:00" in rota  # offset explícito, sempre
    assert resposta["periodo_consultado"].startswith(("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"))


async def test_data_ambigua_vira_pergunta_e_nao_chamada(agenda_falsa, ctx):
    """O risco §16 em um teste: o conector não chuta o mês, e a agenda nem
    chega a ser chamada."""
    antes = len(agenda_falsa.chamadas)
    with pytest.raises(ToolError) as e:
        await servidor.agenda_consultar_slots(ctx, service_id="s1", quando="quando der")
    assert "Pergunte ao cliente" in str(e.value)
    assert len(agenda_falsa.chamadas) == antes


async def test_sem_horario_a_resposta_empurra_para_a_fila(agenda_falsa, ctx):
    """'Não tem' não é resposta aceitável para um cliente que quer marcar."""
    agenda_falsa.padrao = []
    resposta = await servidor.agenda_consultar_slots(ctx, service_id="s1", quando="amanhã")
    assert "fila" in resposta["sugestao"]


async def test_meu_dia_nao_precisa_de_telefone_na_sessao(agenda_falsa, ctx):
    agenda_falsa.padrao = []
    await servidor.agenda_meu_dia(ctx)
    (_, rota, _) = agenda_falsa.chamadas[-1]
    assert rota == "/appointments/meus"  # a sessão já diz de quem se trata


async def test_agendar_devolve_texto_pronto_para_falar(agenda_falsa, ctx):
    agenda_falsa.responder(
        "POST", "/appointments", 201, {"id": "ap1", "label_humano": "quinta, 11 de março, 15h"}
    )
    resposta = await servidor.agenda_agendar(
        ctx, service_id="s1", inicio="2027-03-11T15:00:00-03:00", cliente_nome="Ana"
    )
    assert resposta["agendado"] is True
    assert "quinta, 11 de março, 15h" in resposta["para_falar"]


async def test_slot_ocupado_sobe_com_as_alternativas(agenda_falsa, ctx):
    agenda_falsa.responder(
        "POST",
        "/appointments",
        409,
        {
            "code": "SLOT_INDISPONIVEL",
            "message": "O horário pedido já está ocupado ou fora da grade.",
            "hint": "Ofereça estas alternativas ao cliente: quinta, 11 de março, 16h30.",
            "alternativas": [{"inicio": "…", "label_humano": "quinta, 11 de março, 16h30"}],
        },
    )
    with pytest.raises(ToolError) as e:
        await servidor.agenda_agendar(
            ctx, service_id="s1", inicio="2027-03-11T15:00:00-03:00", cliente_nome="Ana"
        )
    # o agente se recupera sem uma segunda chamada
    assert "16h30" in str(e.value)


async def test_fila_de_espera_avisa_que_nao_ha_reserva(agenda_falsa, ctx):
    agenda_falsa.responder("POST", "/waitlist", 201, {"id": "w1"})
    resposta = await servidor.agenda_fila_espera(
        ctx, service_id="s1", cliente_nome="Ana", quando="quinta à tarde"
    )
    assert "não fica reservado" in resposta["para_falar"]
    (_, _, _) = agenda_falsa.chamadas[-1]


async def test_reagendar_fala_do_horario_liberado(agenda_falsa, ctx):
    agenda_falsa.responder(
        "POST", "/appointments/ap1/reschedule", 200, {"label_humano": "sexta, 12 de março, 10h"}
    )
    resposta = await servidor.agenda_reagendar(
        ctx, appointment_id="ap1", novo_inicio="2027-03-12T10:00:00-03:00"
    )
    assert "liberado" in resposta["para_falar"]


async def test_sessao_expirada_manda_pedir_mensagem_nova(agenda_falsa, ctx):
    """Um 401 cru faria o modelo tentar de novo com outros argumentos. A
    tradução diz a única coisa que resolve: esperar o cliente escrever."""
    agenda_falsa.responder(
        "GET",
        "/appointments/meus",
        401,
        {
            "code": "SESSAO_INVALIDA",
            "message": "Token de sessão de atendimento inválido: expirado",
            "hint": "…",
        },
    )
    with pytest.raises(ToolError) as e:
        await servidor.agenda_meu_dia(ctx)
    assert "mensagem nova" in str(e.value)
