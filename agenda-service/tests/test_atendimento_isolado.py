"""RF-19 — o agente de atendimento alcança UM cliente, e só ele.

Antes disto, quem conversava com o cliente no WhatsApp tinha a agenda inteira
da organização: nome, telefone e observações de todo mundo, a fila completa,
e `/appointments/proximo` como rota de enumeração — um telefone por chamada.
Cada teste aqui corresponde a uma dessas portas.
"""

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app import enderecos
from app.auth import Credencial, credencial_atual, escopos_do_papel
from app.errors import ApiError
from app.main import app
from app.sessao_atendimento import emitir, validar

from .conftest import integracao

TITULAR = "+5511999998888"
OUTRO = "+5511777776666"


# ── Endereço canônico: o pré-requisito de tudo ───────────────────────────────


@pytest.mark.parametrize(
    "bruto,esperado",
    [
        ("+55 11 99876-5432", "+5511998765432"),
        ("(11) 99876-5432", "+11998765432"),
        ("+5511998765432", "+5511998765432"),
        ("tg:123456789", "tg:123456789"),
        ("TG: 123456789", "tg:123456789"),
        ("", ""),
    ],
)
def test_normalizar_e_a_mesma_regua_para_todos(bruto, esperado):
    assert enderecos.normalizar(bruto) == esperado
    # Idempotente: o backfill roda uma vez, a escrita roda sempre.
    assert enderecos.normalizar(enderecos.normalizar(bruto)) == enderecos.normalizar(bruto)


def test_espaco_no_telefone_nao_tira_o_cliente_do_proprio_horario():
    """O modo de falha que a normalização existe para evitar: o cliente
    pergunta pelo próprio horário e ouve 'não achei nada no seu nome'."""
    assert enderecos.mesmo("+55 11 99876-5432", "+5511998765432")
    assert not enderecos.mesmo("+5511998765432", "+5511777776666")


# ── O token: formato, domínio e teto ─────────────────────────────────────────

DOMINIO = b"cpdf.sessao-atendimento.v1"


def _cunhar_como_o_canal(org_id, titular, *, exp_delta=1800, escopos=None, dominio=DOMINIO):
    """Reimplementação deliberada do que `canal-service` faz — o formato do
    token é contrato entre dois deployables sem biblioteca comum, e é este
    par de testes (aqui e em canal-service/tests/test_sessao_atendimento.py)
    que impede os dois lados de divergirem em silêncio."""
    from app.config import settings

    corpo = json.dumps(
        {
            "org": str(org_id),
            "tit": titular,
            "esc": sorted(escopos or ["agenda:read", "agenda:write"]),
            "jti": "vetor",
            "exp": int(datetime.now(UTC).timestamp()) + exp_delta,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    assinatura = hmac.new(
        settings().sessao_atendimento_secret.encode(), dominio + b"|" + corpo, hashlib.sha256
    ).hexdigest()
    return "ats_" + base64.urlsafe_b64encode(corpo).decode().rstrip("=") + "." + assinatura


def test_a_agenda_aceita_o_token_que_o_canal_cunha():
    org = uuid.uuid4()
    sessao = validar(_cunhar_como_o_canal(org, TITULAR))
    assert sessao.org_id == org
    assert sessao.titular == TITULAR
    assert sessao.escopos == escopos_do_papel("atendimento")


def test_token_de_sessao_nao_serve_como_confirmation_token():
    """Os dois assinam com HMAC. Sem prefixo de domínio, um token válido de um
    passaria pelo outro sempre que os segredos coincidissem — e coincidir é o
    que acontece quando alguém reusa SUPABASE_JWT_SECRET por conveniência."""
    from app import confirmacao

    alvo = uuid.uuid4()
    with pytest.raises(ApiError) as erro:
        validar(confirmacao.gerar_token("cancel", alvo))
    assert erro.value.code == "SESSAO_INVALIDA"

    # E o contrário: o corpo do token de sessão assinado no domínio errado
    # (o de outro uso de HMAC) é recusado.
    with pytest.raises(ApiError):
        validar(_cunhar_como_o_canal(uuid.uuid4(), TITULAR, dominio=b"outro.dominio"))


def test_token_expirado_e_recusado():
    with pytest.raises(ApiError) as erro:
        validar(_cunhar_como_o_canal(uuid.uuid4(), TITULAR, exp_delta=-1))
    assert erro.value.code == "SESSAO_INVALIDA"


def test_escopo_reivindicado_a_mais_e_aparado_no_teto():
    """Os escopos vêm assinados, mas atendimento é o teto: nem uma cunhagem
    (legítima ou não) com `agenda:admin` dentro alcança rota administrativa."""
    token = _cunhar_como_o_canal(
        uuid.uuid4(), TITULAR, escopos=["agenda:read", "agenda:write", "agenda:admin", "canal:admin"]
    )
    assert validar(token).escopos == escopos_do_papel("atendimento")


def test_emitir_normaliza_o_titular():
    assert validar(emitir(uuid.uuid4(), "+55 11 99876-5432")).titular == "+5511998765432"


# ── As guardas, contra o banco ───────────────────────────────────────────────

@pytest.fixture()
def como_titular(org_id):
    """Uma sessão de atendimento: read + write, e um titular provado."""

    def usar(telefone=TITULAR):
        app.dependency_overrides[credencial_atual] = lambda: Credencial(
            org_id=org_id,
            escopos=escopos_do_papel("atendimento"),
            ator="agente",
            titular=telefone,
            nome="atendimento",
        )

    usar()
    yield usar
    app.dependency_overrides.pop(credencial_atual, None)


def _agendar(client, catalogo, telefone, nome="Fulano", observacoes=None, hora=13):
    # Um recurso só no catálogo: horários distintos por cliente, senão o
    # conflito de agenda (que é outro teste) atrapalha este aqui.
    quando = datetime.now(UTC) + timedelta(days=2)
    quando = quando.replace(hour=hora, minute=0, second=0, microsecond=0)
    while quando.weekday() > 4:
        quando += timedelta(days=1)
    corpo = {
        "service_id": catalogo["servico"]["id"],
        "inicio": quando.isoformat(),
        "cliente_nome": nome,
        "cliente_telefone": telefone,
    }
    if observacoes:
        corpo["observacoes"] = observacoes
    resposta = client.post("/appointments", json=corpo)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


@integracao
def test_titular_recebe_404_no_compromisso_de_outro(client, catalogo, como_titular):
    """404 e não 403: 'existe, mas não é seu' já confirma a existência."""
    como_titular(OUTRO)
    do_outro = _agendar(client, catalogo, OUTRO, nome="Beltrano", hora=14)
    como_titular(TITULAR)

    for metodo, rota in [
        ("get", f"/appointments/{do_outro['id']}/history"),
        ("post", f"/appointments/{do_outro['id']}/confirm"),
    ]:
        resposta = getattr(client, metodo)(rota)
        assert resposta.status_code == 404, f"{metodo} {rota}"
        assert resposta.json()["code"] == "NAO_ENCONTRADO"

    resposta = client.post(
        f"/appointments/{do_outro['id']}/reschedule",
        json={"novo_inicio": (datetime.now(UTC) + timedelta(days=5)).isoformat()},
    )
    assert resposta.status_code == 404


@integracao
def test_o_proprio_compromisso_continua_alcancavel(client, catalogo, como_titular):
    meu = _agendar(client, catalogo, TITULAR)
    assert client.post(f"/appointments/{meu['id']}/confirm").status_code == 200


@integracao
def test_espaco_no_telefone_nao_derruba_o_acesso(client, catalogo, como_titular):
    """A escrita normaliza, o titular normaliza — as duas pontas se encontram."""
    meu = _agendar(client, catalogo, "+55 11 99999-8888")
    assert meu["cliente_telefone"] == TITULAR
    assert client.post(f"/appointments/{meu['id']}/confirm").status_code == 200


@integracao
def test_escrita_em_nome_de_terceiro_e_recusada(client, catalogo, como_titular):
    quando = (datetime.now(UTC) + timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)
    resposta = client.post(
        "/appointments",
        json={
            "service_id": catalogo["servico"]["id"],
            "inicio": quando.isoformat(),
            "cliente_nome": "Beltrano",
            "cliente_telefone": OUTRO,
        },
    )
    assert resposta.status_code == 403
    assert resposta.json()["code"] == "TITULAR_DIVERGENTE"


@integracao
def test_proximo_ignora_o_parametro_e_responde_pelo_titular(client, catalogo, como_titular):
    """Sem isso a rota é enumeração: um telefone por chamada, e o agente
    reconstrói a agenda inteira sem nunca sair do escopo `agenda:read`."""
    como_titular(OUTRO)
    _agendar(client, catalogo, OUTRO, nome="Beltrano", hora=14)
    como_titular(TITULAR)
    assert client.get(f"/appointments/proximo?telefone={OUTRO}").status_code == 404


@integracao
def test_fila_vem_ja_filtrada(client, catalogo, como_titular, canal_fake):
    janela_ini = (datetime.now(UTC) + timedelta(days=4)).replace(hour=12, minute=0, second=0, microsecond=0)
    janela_fim = janela_ini + timedelta(hours=6)

    def entrar(telefone, nome):
        return client.post(
            "/waitlist",
            json={
                "service_id": catalogo["servico"]["id"],
                "cliente_nome": nome,
                "cliente_telefone": telefone,
                "janela_inicio": janela_ini.isoformat(),
                "janela_fim": janela_fim.isoformat(),
            },
        )

    como_titular(OUTRO)
    do_outro = entrar(OUTRO, "Beltrano")
    assert do_outro.status_code == 201, do_outro.text

    como_titular(TITULAR)
    assert entrar(TITULAR, "Fulano").status_code == 201

    fila = client.get("/waitlist").json()
    assert [e["cliente_telefone"] for e in fila] == [TITULAR]
    # E a entrada alheia, mesmo com o id em mãos, não é alcançável.
    assert client.delete(f"/waitlist/{do_outro.json()['id']}").status_code == 404


@integracao
def test_sem_operacao_nao_ve_risco_nem_observacoes(client, catalogo, org_id):
    """Posse do registro não autoriza tudo que há nele: risco de falta e
    observações são dados PRODUZIDOS pela operação sobre o cliente. Um bot
    dizendo 'você é risco alto de faltar' é dano, não transparência."""
    meu = _agendar(client, catalogo, TITULAR, observacoes="cliente costuma atrasar")
    assert meu["observacoes"] == "cliente costuma atrasar"  # X-Org-Id = autoridade total

    app.dependency_overrides[credencial_atual] = lambda: Credencial(
        org_id=org_id,
        escopos=escopos_do_papel("atendimento"),
        ator="agente",
        titular=TITULAR,
        nome="atendimento",
    )
    try:
        visto = client.post(f"/appointments/{meu['id']}/confirm").json()
        assert visto["id"] == meu["id"]
        assert visto["observacoes"] is None
        assert visto["risco_no_show"] is None
        assert visto["risco_detalhe"] is None
    finally:
        app.dependency_overrides.pop(credencial_atual, None)


@integracao
def test_bearer_de_sessao_de_verdade_atravessa_a_pilha(client, catalogo, org_id):
    """Sem override de dependência: o token entra pelo header, como em produção."""
    meu = _agendar(client, catalogo, TITULAR)
    do_outro = _agendar(client, catalogo, OUTRO, nome="Beltrano", hora=14)

    cabecalho = {"Authorization": f"Bearer {emitir(org_id, TITULAR)}"}
    assert client.post(f"/appointments/{meu['id']}/confirm", headers=cabecalho).status_code == 200
    assert (
        client.get(f"/appointments/{do_outro['id']}/history", headers=cabecalho).status_code == 404
    )
    # Escopo continua valendo: atendimento não enxerga a operação.
    assert client.get("/agenda/day?date=2026-08-27", headers=cabecalho).status_code == 403


@integracao
def test_token_adulterado_nao_entra(client, org_id):
    token = emitir(org_id, TITULAR)
    corpo, assinatura = token.removeprefix("ats_").split(".")
    forjado = json.loads(base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4)))
    forjado["tit"] = OUTRO
    novo = base64.urlsafe_b64encode(
        json.dumps(forjado, separators=(",", ":"), sort_keys=True).encode()
    ).decode().rstrip("=")
    resposta = client.get(
        "/appointments/proximo?telefone=" + OUTRO,
        headers={"Authorization": f"Bearer ats_{novo}.{assinatura}"},
    )
    assert resposta.status_code == 401
    assert resposta.json()["code"] == "SESSAO_INVALIDA"


# ── A virada: a chave de serviço deixa de valer ──────────────────────────────


@pytest.fixture()
def chave_de_servico(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings(), "agenda_service_key", "chave-do-servico")
    return {"X-Service-Key": "chave-do-servico", "X-Org-Id": str(uuid.uuid4())}


@integracao
def test_flag_desligada_mantem_o_caminho_legado(client, chave_de_servico, monkeypatch):
    """Enquanto o canal antigo estiver em pé, a chave ainda passa — é o que
    torna a virada uma configuração e não um deploy sincronizado."""
    from app.config import settings

    monkeypatch.setattr(settings(), "atendimento_isolado", False)
    assert client.get("/services", headers=chave_de_servico).status_code == 200


@integracao
def test_flag_ligada_fecha_a_chave_de_servico(client, chave_de_servico, monkeypatch):
    """Com a flag ligada, a chave que valia pela organização inteira morre:
    todo atendimento passa a precisar do token de sessão."""
    from app.config import settings

    monkeypatch.setattr(settings(), "atendimento_isolado", True)
    resposta = client.get("/services", headers=chave_de_servico)
    assert resposta.status_code == 401
    assert resposta.json()["code"] == "NAO_AUTENTICADO"
