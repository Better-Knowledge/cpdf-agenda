"""Opt-out é regra determinística — sair do spam não depende de IA acertar."""

from app.optout import e_pedido_de_optout


def test_variacoes_de_sair_sao_detectadas():
    for texto in ["SAIR", "sair", "Sair.", " sair ", "PARE", "parar", "Não quero mais receber"]:
        assert e_pedido_de_optout(texto), texto


def test_frases_que_contem_sair_nao_disparam():
    for texto in ["quero sair mais cedo amanhã", "posso sair do horário das 15h?", "confirmo"]:
        assert not e_pedido_de_optout(texto), texto
