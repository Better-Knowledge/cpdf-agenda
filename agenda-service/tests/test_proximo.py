"""Apoio ao agente (etapa 6): próximo compromisso por telefone e credencial
service-to-service (X-Service-Key + X-Org-Id, ator=agente)."""

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


def test_service_key_autentica_como_agente(client, catalogo, org_id, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings(), "agenda_service_key", "chave-servico-teste")
    ap = _agendar(client, catalogo, "2027-03-12T10:00:00-03:00")

    cabecalhos = {"X-Service-Key": "chave-servico-teste", "X-Org-Id": str(org_id)}
    corpo = client.get(
        "/appointments/proximo", params={"telefone": TELEFONE}, headers=cabecalhos
    ).json()
    assert corpo["id"] == ap["id"]

    # ator=agente: cancelar exige o fluxo propor → confirmar
    primeira = client.post(
        f"/appointments/{ap['id']}/cancel", json={"motivo": "cliente pediu"}, headers=cabecalhos
    )
    assert primeira.status_code == 409
    assert primeira.json()["code"] == "CONFIRMACAO_NECESSARIA"

    # chave errada não passa
    negada = client.get(
        "/appointments/proximo",
        params={"telefone": TELEFONE},
        headers={"X-Service-Key": "errada", "X-Org-Id": str(org_id)},
    )
    assert negada.status_code == 401
