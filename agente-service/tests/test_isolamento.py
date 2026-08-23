"""RF-19 — o agente perde autoridade própria na agenda.

Antes disto ele se apresentava com `X-Service-Key` + `X-Org-Id`: autoridade
sobre a organização inteira, e o cliente em nome de quem agia era um detalhe
que ele próprio informava. Agora a autoridade é o token que o canal cunhou
depois de provar o endereço — e o agente não tem como falar por outra pessoa
nem que queira.
"""

import uuid

from app.clientes import Sessao
from app.fluxo import tratar

from .conftest import COMPROMISSO

ORG = uuid.uuid4()
TEL = "+5511999998888"


def test_sessao_isolada_apresenta_o_token_e_nada_mais():
    cabecalhos = Sessao(org_id=ORG, telefone=TEL, token="ats_abc")._cabecalhos_agenda()
    assert cabecalhos == {"Authorization": "Bearer ats_abc"}
    # Nem a chave de serviço nem a org viajam junto: se o token não bastar, a
    # chamada falha — que é o comportamento certo, não um fallback silencioso.
    assert "X-Service-Key" not in cabecalhos
    assert "X-Org-Id" not in cabecalhos


def test_sem_token_o_agente_cai_no_caminho_legado(monkeypatch):
    """Enquanto houver canal antigo em produção. É este caminho que a flag
    ATENDIMENTO_ISOLADO fecha do lado da agenda."""
    from app.config import settings

    monkeypatch.setattr(settings(), "agenda_service_key", "chave-legada")
    cabecalhos = Sessao(org_id=ORG, telefone=TEL)._cabecalhos_agenda()
    assert cabecalhos["X-Service-Key"] == "chave-legada"
    assert cabecalhos["X-Org-Id"] == str(ORG)


def test_toda_chamada_a_agenda_leva_a_sessao(agenda_falsa):
    agenda_falsa.compromisso = COMPROMISSO
    sessao = Sessao(org_id=ORG, telefone=TEL, token="ats_abc")
    tratar(sessao, "confirmo")

    assert agenda_falsa.chamadas, "o agente nem chamou a agenda"
    assert all(s is sessao for s in agenda_falsa.sessoes)


def test_fila_vem_ja_filtrada_e_o_agente_confia_nisso(agenda_falsa):
    """Com sessão isolada, a agenda devolve só as entradas do titular. O
    agente não refiltra — e é isso que se quer provar: a defesa não depende
    mais de ele lembrar de filtrar, que é como a fila vazava."""
    agenda_falsa.fila = [
        {"id": "e1", "cliente_telefone": TEL, "status": "ofertado", "slot_ofertado": "x"}
    ]
    agenda_falsa.aceite = (200, {**COMPROMISSO, "id": "novo", "label_humano": "quinta, 15h30"})

    resultado = tratar(Sessao(org_id=ORG, telefone=TEL, token="ats_abc"), "quero")
    assert resultado.acao == "agendado"
    assert ("GET", "/waitlist") in agenda_falsa.chamadas


def test_no_modo_legado_o_filtro_local_continua(agenda_falsa):
    """Sem token, a agenda devolve a fila inteira — e aí o filtro por telefone
    ainda é a única coisa entre o cliente e a oferta de um estranho."""
    agenda_falsa.fila = [
        {"id": "alheia", "cliente_telefone": "+5511777776666", "status": "ofertado"}
    ]
    resultado = tratar(Sessao(org_id=ORG, telefone=TEL), "quero")
    assert resultado.acao == "esclarecimento"
    assert "não encontrei uma oferta" in (resultado.resposta or "").lower()


def test_a_resposta_vai_para_quem_escreveu(monkeypatch):
    """`responder` tira o destinatário da sessão. Não há assinatura possível
    em que o agente mande mensagem para um terceiro."""
    from app import clientes

    enviados = []
    monkeypatch.setattr(clientes, "canal", lambda m, r, o, c=None: (enviados.append(c), (200, {}))[1])
    clientes.responder(Sessao(org_id=ORG, telefone=TEL, token="ats_abc"), "oi")
    assert enviados == [{"destinatario": TEL, "tipo": "sessao", "texto": "oi"}]
