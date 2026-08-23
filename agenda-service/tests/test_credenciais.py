"""Fundação de papéis e escopos.

A propriedade central desta etapa é chata e essencial: a autoridade agora vem
da credencial, e não de um default global. Os testes provam isso pelos dois
lados — o legado continua funcionando, e o novo caminho concede exatamente o
que a linha do banco diz.
"""

import uuid

import pytest

from app.auth import (
    ESCOPOS_HUMANO,
    PAPEIS,
    Credencial,
    escopos_do_papel,
    exigir_escopo,
    gerar_token,
    hash_token,
    limpar_cache,
    validar_escopos,
)
from app.errors import ApiError

from .conftest import integracao


@pytest.fixture(autouse=True)
def _cache_limpo():
    """O cache de credencial tem TTL de 30 s — entre testes ele precisa sumir,
    senão uma credencial revogada num teste continua válida no seguinte."""
    limpar_cache()
    yield
    limpar_cache()


# ── Vocabulário (sem banco) ──────────────────────────────────────────────────


def test_atendimento_nao_cancela():
    """Aceite do PRD §14.4: credencial com read+write NÃO consegue cancelar."""
    assert escopos_do_papel("atendimento") == {"agenda:read", "agenda:write"}
    cred = Credencial(org_id=uuid.uuid4(), escopos=escopos_do_papel("atendimento"))
    with pytest.raises(ApiError) as e:
        exigir_escopo(cred, "agenda:cancel")
    assert e.value.code == "ESCOPO_INSUFICIENTE"
    assert e.value.status_code == 403


def test_atendimento_nao_alcanca_nada_administrativo():
    cred = Credencial(org_id=uuid.uuid4(), escopos=escopos_do_papel("atendimento"))
    for escopo in ("agenda:operacao", "agenda:admin", "canal:admin", "credenciais:admin"):
        with pytest.raises(ApiError):
            exigir_escopo(cred, escopo)


def test_nenhum_papel_de_agente_gere_credenciais():
    """Um token administrativo comprometido não pode emitir outro token para
    sobreviver à própria revogação — por isso credenciais:admin fica fora de
    todo preset de bearer."""
    for papel, escopos in PAPEIS.items():
        assert "credenciais:admin" not in escopos, papel
    assert "credenciais:admin" in ESCOPOS_HUMANO  # só o humano por JWT


def test_papeis_sao_crescentes():
    assert PAPEIS["atendimento"] < PAPEIS["operacao"] < PAPEIS["administrativo"]


def test_escopo_desconhecido_e_recusado():
    with pytest.raises(ValueError, match="desconhecidos"):
        validar_escopos(["agenda:read", "agenda:tudo"])
    assert validar_escopos(["agenda:write", "agenda:read", "agenda:read"]) == [
        "agenda:read", "agenda:write",
    ]


def test_token_e_hash_nao_sao_o_mesmo_valor():
    token, h, prefixo = gerar_token()
    assert token.startswith("agk_")
    assert h == hash_token(token)
    assert token not in h
    assert prefixo == token[:10] and len(prefixo) < len(token)


# ── Lookup no banco ──────────────────────────────────────────────────────────


@integracao
def test_credencial_do_banco_concede_exatamente_os_escopos_da_linha(client, org_id):
    from app.admin_cli import emitir
    from app.auth import _resolver_credencial

    token = emitir(org_id, "Bot do canal", "atendimento")
    cred = _resolver_credencial(token)

    assert cred is not None
    assert cred.org_id == org_id
    assert cred.escopos == PAPEIS["atendimento"]
    assert cred.ator == "agente"
    assert cred.nome == "Bot do canal"


@integracao
def test_escopos_sobrepoem_o_papel(banco_migrado, org_id):
    """O papel é preset; quem manda é a coluna. É o que permite ao
    administrador ajustar credencial a credencial."""
    from app.admin_cli import emitir
    from app.auth import _resolver_credencial

    token = emitir(org_id, "Só leitura", "administrativo", escopos=["agenda:read"])
    cred = _resolver_credencial(token)
    assert cred.escopos == frozenset({"agenda:read"})


@integracao
def test_revogada_deixa_de_autenticar(banco_migrado, org_id):
    from app.admin_cli import emitir, listar, revogar
    from app.auth import _resolver_credencial

    token = emitir(org_id, "Temporária", "operacao")
    assert _resolver_credencial(token) is not None

    limpar_cache()  # o cache tem TTL de 30 s; sem limpar, a revogação demora
    (linha,) = [c for c in listar(org_id) if c.nome == "Temporária"]
    assert revogar(linha.id) is True
    assert _resolver_credencial(token) is None


@integracao
def test_token_desconhecido_nao_autentica(banco_migrado, org_id):
    from app.auth import _resolver_credencial

    assert _resolver_credencial("agk_nunca-emitido") is None


@integracao
def test_lookup_nao_deixa_a_sessao_em_modo_worker(client, org_id):
    """O lookup usa modo worker (é o token que revela a org). Se ele vazasse
    para a sessão da requisição, TODA query seguinte atravessaria organizações
    — que é exatamente o que a RLS existe para impedir."""
    from app.admin_cli import emitir
    from app.auth import _resolver_credencial
    from app.sessao import SessionLocal

    outra_org = uuid.uuid4()
    emitir(outra_org, "De outra org", "administrativo")
    token = emitir(org_id, "Desta org", "administrativo")
    _resolver_credencial(token)

    # uma sessão nova, sem contexto, não pode enxergar nada
    from sqlalchemy import func, select

    from app.models import AgentCredential

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AgentCredential)) == 0


@integracao
def test_bearer_agk_autentica_pela_api(client, org_id, catalogo):
    from app.admin_cli import emitir

    token = emitir(org_id, "Painel", "administrativo")
    resposta = client.get(
        "/credenciais/eu", headers={"Authorization": f"Bearer {token}", "X-Org-Id": ""}
    )
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["org_id"] == str(org_id)
    assert corpo["papel"] == "administrativo"
    assert corpo["ator"] == "agente"
    assert "credenciais:admin" not in corpo["escopos"]


@integracao
def test_whoami_nunca_devolve_o_token(client, org_id):
    from app.admin_cli import emitir

    token = emitir(org_id, "Painel", "operacao")
    corpo = client.get("/credenciais/eu", headers={"Authorization": f"Bearer {token}"}).json()
    import json

    assert token not in json.dumps(corpo)
    assert "token_hash" not in json.dumps(corpo)


@integracao
def test_bearer_invalido_devolve_401(client):
    resposta = client.get(
        "/credenciais/eu", headers={"Authorization": "Bearer agk_chutado", "X-Org-Id": ""}
    )
    assert resposta.status_code == 401
    assert resposta.json()["code"] == "NAO_AUTENTICADO"


@integracao
def test_credencial_legada_mantem_autoridade_total(client, catalogo):
    """Compatibilidade: o protótipo em produção usa X-Org-Id/X-Agent-Key e não
    pode quebrar nesta etapa. O aperto vem atrás da flag, na etapa 3."""
    assert client.get("/services").status_code == 200
    assert client.get("/waitlist").status_code == 200
    resposta = client.post(
        "/resources", json={"nome": "Sala legada", "tipo": "sala"}
    )
    assert resposta.status_code == 201
