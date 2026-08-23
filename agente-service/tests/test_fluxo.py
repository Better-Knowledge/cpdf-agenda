"""O gradiente de risco, testado: reversível age, negócio propõe,
irreversível vai para o humano."""

import uuid

from app.fluxo import tratar

from .conftest import COMPROMISSO

ORG = uuid.uuid4()
TEL = "+5511955554444"


def test_confirmar_e_automatico(agenda_falsa):
    agenda_falsa.compromisso = COMPROMISSO
    resultado = tratar(ORG, TEL, "confirmo")

    assert resultado.acao == "confirmado"
    assert ("POST", f"/appointments/{COMPROMISSO['id']}/confirm") in agenda_falsa.chamadas
    assert "quinta, 27 de agosto, 15h30" in agenda_falsa.respostas[0]


def test_remarcar_propoe_e_nao_move_nada(agenda_falsa):
    agenda_falsa.compromisso = COMPROMISSO
    agenda_falsa.slots = [
        {"inicio": "2026-08-28T09:00:00-03:00", "label_humano": "sexta, 28 de agosto, 9h"},
        {"inicio": "2026-08-28T10:00:00-03:00", "label_humano": "sexta, 28 de agosto, 10h"},
    ]
    resultado = tratar(ORG, TEL, "preciso remarcar")

    assert resultado.acao == "proposto"
    assert "sexta, 28 de agosto, 9h" in agenda_falsa.respostas[0]
    # propôs, mas NÃO reagendou sozinho
    assert not any("reschedule" in rota for _, rota in agenda_falsa.chamadas)


def test_urls_escapam_offset_e_telefone(agenda_falsa):
    """'+' cru numa query string vira espaço: o offset do horário e o telefone
    E.164 precisam ir escapados, senão a agenda responde 422."""
    agenda_falsa.compromisso = COMPROMISSO
    agenda_falsa.slots = [
        {"inicio": "2026-08-28T09:00:00-03:00", "label_humano": "sexta, 28 de agosto, 9h"}
    ]
    tratar(ORG, TEL, "quero remarcar")

    for _, rota in agenda_falsa.chamadas:
        assert "+" not in rota, f"'+' não escapado em {rota}"
    assert any("%2B" in rota for _, rota in agenda_falsa.chamadas)  # telefone escapado
    assert any("from=" in rota and "%2B00%3A00" in rota for _, rota in agenda_falsa.chamadas)


def test_cancelar_nunca_e_automatico(agenda_falsa):
    agenda_falsa.compromisso = COMPROMISSO
    resultado = tratar(ORG, TEL, "quero cancelar")

    assert resultado.acao == "aguardando_humano"
    assert not any("cancel" in rota for _, rota in agenda_falsa.chamadas)
    assert "equipe" in agenda_falsa.respostas[0]


def test_fallback_em_duas_etapas(agenda_falsa):
    agenda_falsa.compromisso = COMPROMISSO

    primeira = tratar(ORG, TEL, "hmmm sei lá")
    assert primeira.acao == "esclarecimento"
    assert "confirmar" in agenda_falsa.respostas[0]

    segunda = tratar(ORG, TEL, "???")
    assert segunda.acao == "aguardando_humano"


def test_esclarecimento_zera_apos_acerto(agenda_falsa):
    agenda_falsa.compromisso = COMPROMISSO
    assert tratar(ORG, TEL, "???").acao == "esclarecimento"
    assert tratar(ORG, TEL, "confirmo").acao == "confirmado"
    # a contagem zerou: a próxima dúvida volta a ser esclarecimento, não humano
    assert tratar(ORG, TEL, "???").acao == "esclarecimento"


def test_sem_compromisso_o_agente_oferece_marcar(agenda_falsa):
    agenda_falsa.compromisso = None
    resultado = tratar(ORG, TEL, "confirmo")
    assert resultado.acao == "esclarecimento"
    assert "marcar" in agenda_falsa.respostas[0]


def test_remarcar_sem_horarios_livres_vai_para_humano(agenda_falsa):
    agenda_falsa.compromisso = COMPROMISSO
    agenda_falsa.slots = []
    assert tratar(ORG, TEL, "quero remarcar").acao == "aguardando_humano"
