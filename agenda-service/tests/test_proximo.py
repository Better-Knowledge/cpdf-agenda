# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Próximo compromisso por telefone — e o que sobrou da credencial de serviço.

`X-Service-Key` foi como o agente falou com a agenda até o RF-19: uma chave de
ambiente com autoridade sobre a organização inteira, dizendo em cada pedido
por qual cliente agia. Hoje ela é alavanca de rollback, não caminho suportado:
`atendimento_isolado` vem ligado e a fecha.
"""

from .conftest import integracao

pytestmark = integracao

TELEFONE = "+5511988887777"


def _agendar(client, catalogo, inicio: str, telefone: str = TELEFONE):
    resposta = client.post(
        "/appointments",
        json={
            "service_id": catalogo["servico"]["id"],
            "resource_id": catalogo["recurso"]["id"],
            "inicio": inicio,
            "cliente_nome": "Cliente do Zap",
            "cliente_telefone": telefone,
        },
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def test_proximo_devolve_o_mais_cedo_no_futuro(client, catalogo):
    _agendar(client, catalogo, "2027-03-10T10:00:00-03:00")  # quarta
    mais_cedo = _agendar(client, catalogo, "2027-03-09T10:00:00-03:00")  # terça

    corpo = client.get("/appointments/proximo", params={"telefone": TELEFONE}).json()
    assert corpo["id"] == mais_cedo["id"]
    assert corpo["label_humano"].startswith("terça")


def test_proximo_ignora_cancelados_e_telefone_sem_nada_e_404(client, catalogo):
    ap = _agendar(client, catalogo, "2027-03-11T10:00:00-03:00")
    assert client.post(f"/appointments/{ap['id']}/cancel", json={"motivo": "x"}).status_code == 200

    resposta = client.get("/appointments/proximo", params={"telefone": TELEFONE})
    assert resposta.status_code == 404
    assert resposta.json()["code"] == "NAO_ENCONTRADO"


def _com_chave_de_servico(monkeypatch, org_id, isolado: bool):
    from app.config import settings

    monkeypatch.setattr(settings(), "agenda_service_key", "chave-servico-teste")
    monkeypatch.setattr(settings(), "atendimento_isolado", isolado)
    return {"X-Service-Key": "chave-servico-teste", "X-Org-Id": str(org_id)}


def test_service_key_nao_vale_mais_por_padrao(client, catalogo, org_id, monkeypatch):
    """A virada do RF-19. Um único segredo de ambiente deixou de conceder
    acesso a todos os clientes da organização — quem atende usa o token de
    sessão que o canal cunha depois de provar o endereço."""
    cabecalhos = _com_chave_de_servico(monkeypatch, org_id, isolado=True)
    resposta = client.get("/appointments/proximo", params={"telefone": TELEFONE}, headers=cabecalhos)
    assert resposta.status_code == 401
    assert resposta.json()["code"] == "NAO_AUTENTICADO"
    assert "ATENDIMENTO_ISOLADO" in resposta.json()["message"]


def test_com_a_flag_desligada_o_caminho_antigo_volta(client, catalogo, org_id, monkeypatch):
    """A alavanca de rollback existe para um deploy que dê errado no meio da
    aula — e continua se comportando como antes, inclusive exigindo confirmação
    humana para cancelar (ator=agente)."""
    cabecalhos = _com_chave_de_servico(monkeypatch, org_id, isolado=False)
    ap = _agendar(client, catalogo, "2027-03-12T10:00:00-03:00")

    corpo = client.get(
        "/appointments/proximo", params={"telefone": TELEFONE}, headers=cabecalhos
    ).json()
    assert corpo["id"] == ap["id"]

    primeira = client.post(
        f"/appointments/{ap['id']}/cancel", json={"motivo": "cliente pediu"}, headers=cabecalhos
    )
    assert primeira.status_code == 409
    assert primeira.json()["code"] == "CONFIRMACAO_NECESSARIA"


def test_chave_de_servico_errada_nunca_passa(client, catalogo, org_id, monkeypatch):
    _com_chave_de_servico(monkeypatch, org_id, isolado=False)
    negada = client.get(
        "/appointments/proximo",
        params={"telefone": TELEFONE},
        headers={"X-Service-Key": "errada", "X-Org-Id": str(org_id)},
    )
    assert negada.status_code == 401
