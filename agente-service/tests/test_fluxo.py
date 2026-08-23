"""O gradiente de risco, testado: reversível age, negócio propõe,
irreversível vai para o humano."""

import uuid

from app.clientes import Sessao
from app.fluxo import tratar

from .conftest import COMPROMISSO

ORG = uuid.uuid4()
TEL = "+5511999998888"


def sessao(telefone: str = TEL, token: str | None = "ats_fake") -> Sessao:
    """Por padrão isolada: é assim que o canal entrega desde o RF-19."""
    return Sessao(org_id=ORG, telefone=telefone, token=token)


def test_confirmar_e_automatico(agenda_falsa):
    agenda_falsa.compromisso = COMPROMISSO
    resultado = tratar(sessao(), "confirmo")

    assert resultado.acao == "confirmado"
    assert ("POST", f"/appointments/{COMPROMISSO['id']}/confirm") in agenda_falsa.chamadas
    assert "quinta, 27 de agosto, 15h30" in agenda_falsa.respostas[0]


def test_remarcar_propoe_e_nao_move_nada(agenda_falsa):
    agenda_falsa.compromisso = COMPROMISSO
    agenda_falsa.slots = [
        {"inicio": "2026-08-28T09:00:00-03:00", "label_humano": "sexta, 28 de agosto, 9h"},
        {"inicio": "2026-08-28T10:00:00-03:00", "label_humano": "sexta, 28 de agosto, 10h"},
    ]
    resultado = tratar(sessao(), "preciso remarcar")

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
    tratar(sessao(), "quero remarcar")

    for _, rota in agenda_falsa.chamadas:
        assert "+" not in rota, f"'+' não escapado em {rota}"
    assert any("%2B" in rota for _, rota in agenda_falsa.chamadas)  # telefone escapado
    assert any("from=" in rota and "%2B00%3A00" in rota for _, rota in agenda_falsa.chamadas)


def test_cancelar_nunca_e_automatico(agenda_falsa):
    agenda_falsa.compromisso = COMPROMISSO
    resultado = tratar(sessao(), "quero cancelar")

    assert resultado.acao == "aguardando_humano"
    assert not any("cancel" in rota for _, rota in agenda_falsa.chamadas)
    assert "equipe" in agenda_falsa.respostas[0]


def test_fallback_em_duas_etapas(agenda_falsa):
    agenda_falsa.compromisso = COMPROMISSO

    primeira = tratar(sessao(), "hmmm sei lá")
    assert primeira.acao == "esclarecimento"
    assert "confirmar" in agenda_falsa.respostas[0]

    segunda = tratar(sessao(), "???")
    assert segunda.acao == "aguardando_humano"


def test_esclarecimento_zera_apos_acerto(agenda_falsa):
    agenda_falsa.compromisso = COMPROMISSO
    assert tratar(sessao(), "???").acao == "esclarecimento"
    assert tratar(sessao(), "confirmo").acao == "confirmado"
    # a contagem zerou: a próxima dúvida volta a ser esclarecimento, não humano
    assert tratar(sessao(), "???").acao == "esclarecimento"


def test_sem_compromisso_o_agente_oferece_marcar(agenda_falsa):
    agenda_falsa.compromisso = None
    resultado = tratar(sessao(), "confirmo")
    assert resultado.acao == "esclarecimento"
    assert "marcar" in agenda_falsa.respostas[0]


def test_pergunta_de_esclarecimento_se_adapta_a_situacao(agenda_falsa):
    """Oferecer 'confirmar ou cancelar' a quem não tem horário é conversa de
    robô — quem chega novo (o caso comum na demo) precisa ouvir 'quer marcar?'."""
    agenda_falsa.compromisso = None
    tratar(sessao(), "bom dia, tudo bem?")
    assert "marcar" in agenda_falsa.respostas[0]
    assert "cancelar" not in agenda_falsa.respostas[0]

    agenda_falsa.respostas.clear()
    agenda_falsa.compromisso = COMPROMISSO
    tratar(sessao("+5511900001111"), "bom dia, tudo bem?")
    assert "confirmar" in agenda_falsa.respostas[0]


def test_endereco_de_telegram_atravessa_o_fluxo(agenda_falsa):
    """O agente não sabe o que é WhatsApp ou Telegram: para ele, endereço é
    endereço — é o canal que traduz."""
    agenda_falsa.compromisso = COMPROMISSO
    resultado = tratar(sessao("tg:987654321"), "confirmo")
    assert resultado.acao == "confirmado"
    assert any("tg%3A987654321" in rota for _, rota in agenda_falsa.chamadas)


def test_remarcar_sem_horarios_livres_vai_para_humano(agenda_falsa):
    agenda_falsa.compromisso = COMPROMISSO
    agenda_falsa.slots = []
    assert tratar(sessao(), "quero remarcar").acao == "aguardando_humano"


# ── RF-14: aceitar a oferta da fila de espera ────────────────────────────────


def test_quero_sozinho_aceita_a_oferta_da_fila(agenda_falsa):
    """O template da oferta pede exatamente 'quero' — a palavra sozinha
    precisa bastar, senão o texto que mandamos não funciona."""
    from .conftest import OFERTA_NA_FILA

    agenda_falsa.compromisso = None
    agenda_falsa.fila = [OFERTA_NA_FILA]
    agenda_falsa.aceite = (200, {"id": "novo", "label_humano": "quinta, 27 de agosto, 15h30"})

    resultado = tratar(sessao(), "quero")
    assert resultado.acao == "agendado"
    assert "quinta, 27 de agosto, 15h30" in agenda_falsa.respostas[0]
    assert ("POST", f"/waitlist/{OFERTA_NA_FILA['id']}/aceitar") in agenda_falsa.chamadas


def test_aceite_que_perde_a_corrida_devolve_alternativas(agenda_falsa):
    """Sem reserva durante a oferta, perder é um caso normal — o cliente
    recebe as 3 opções em vez de um silêncio."""
    from .conftest import OFERTA_NA_FILA

    agenda_falsa.compromisso = None
    agenda_falsa.fila = [OFERTA_NA_FILA]
    agenda_falsa.aceite = (
        409,
        {
            "code": "SLOT_INDISPONIVEL",
            "alternativas": [
                {"label_humano": "sexta, 28 de agosto, 9h"},
                {"label_humano": "sexta, 28 de agosto, 14h"},
                {"label_humano": "segunda, 31 de agosto, 10h"},
            ],
        },
    )

    resultado = tratar(sessao(), "quero")
    assert resultado.acao == "proposto"
    assert "alguém confirmou esse horário antes" in agenda_falsa.respostas[0]
    assert "sexta, 28 de agosto, 9h" in agenda_falsa.respostas[0]


def test_aceite_de_oferta_expirada_explica_sem_culpar_o_cliente(agenda_falsa):
    from .conftest import OFERTA_NA_FILA

    agenda_falsa.compromisso = None
    agenda_falsa.fila = [OFERTA_NA_FILA]
    agenda_falsa.aceite = (409, {"code": "OFERTA_EXPIRADA"})

    resultado = tratar(sessao(), "quero")
    assert resultado.acao == "esclarecimento"
    assert "prazo dessa oferta já passou" in agenda_falsa.respostas[0]


def test_quero_sem_oferta_em_aberto_nao_inventa_agendamento(agenda_falsa):
    agenda_falsa.compromisso = None
    agenda_falsa.fila = []

    resultado = tratar(sessao(), "quero")
    assert resultado.acao == "esclarecimento"
    assert "não encontrei uma oferta" in agenda_falsa.respostas[0].lower()
    assert not any(rota.endswith("/aceitar") for _, rota in agenda_falsa.chamadas)
