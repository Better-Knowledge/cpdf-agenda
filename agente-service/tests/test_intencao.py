# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""IA-04 — a camada determinística: o que é inequívoco não gasta LLM."""

import pytest

from app.intencao import LIMITE_CONFIANCA, classificar, por_regra


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("confirmo", "confirmar"),
        ("Confirmo!", "confirmar"),
        ("sim", "confirmar"),
        ("Beleza", "confirmar"),
        ("tudo certo", "confirmar"),
        ("não vou poder", "cancelar"),
        ("nao posso", "cancelar"),
        ("quero cancelar", "cancelar"),
        ("preciso remarcar", "remarcar"),
        ("da pra mudar pra sexta", "remarcar"),
        ("quero esse horario", "aceitar_oferta"),
    ],
)
def test_regra_pega_o_inequivoco(texto, esperada):
    intencao = por_regra(texto)
    assert intencao is not None, f"{texto!r} deveria bater por regra"
    assert intencao.nome == esperada
    assert intencao.por == "regra"


@pytest.mark.parametrize(
    "texto",
    [
        "não posso confirmar ainda, te falo amanhã",  # nega o confirmar
        "quanto custa o corte?",
        "quem fala?",
        "oi",
    ],
)
def test_regra_nao_chuta(texto):
    assert por_regra(texto) is None


def test_sem_llm_o_nao_reconhecido_fica_abaixo_do_limite():
    """Sem chave de LLM, o que a regra não pega vira dúvida de confiança 0 —
    e o fluxo pergunta em vez de agir."""
    intencao = classificar("quanto custa?")
    assert intencao.confianca < LIMITE_CONFIANCA
    assert intencao.nome == "duvida"


def test_llm_e_consultado_so_quando_a_regra_falha(monkeypatch):
    import app.intencao as mod

    chamou = []

    def llm_fake(texto, contexto=""):
        chamou.append(texto)
        return mod.Intencao(nome="duvida", confianca=0.9, por="llm")

    monkeypatch.setattr(mod, "por_llm", llm_fake)

    assert classificar("confirmo").por == "regra"
    assert chamou == []  # regra resolveu, LLM nem foi acionado

    assert classificar("quanto custa o corte?").por == "llm"
    assert chamou == ["quanto custa o corte?"]
