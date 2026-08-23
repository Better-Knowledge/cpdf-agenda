# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""RF-17 — o OpenAPI é o contrato do módulo.

Estes testes não precisam de banco: validam o schema gerado e garantem que
o artefato versionado (docs/openapi.json) não fica defasado do código.
"""

import json
from pathlib import Path

import pytest

RAIZ_REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def spec() -> dict:
    from app.main import app

    return app.openapi()


def _operacoes(spec: dict):
    for caminho, ops in spec["paths"].items():
        for metodo, op in ops.items():
            yield caminho, metodo, op


def test_security_schemes_declarados(spec):
    schemes = spec["components"]["securitySchemes"]
    assert schemes["SupabaseJWT"]["scheme"] == "bearer"
    assert schemes["AgentKey"]["name"] == "X-Agent-Key"
    assert spec["security"] == [{"SupabaseJWT": []}, {"AgentKey": []}]


def test_toda_rota_declara_escopo_e_erros_de_base(spec):
    for caminho, metodo, op in _operacoes(spec):
        if op.get("security") == []:
            # Rota pública de propósito: `/health`, o feed .ics (o segredo é o
            # token na URL) e o callback do OAuth (quem chama é o navegador
            # redirecionado pelo Google). Sem credencial, declarar escopo ou
            # documentar 401/403 seria mentir sobre o contrato.
            assert not op.get("x-escopo-requerido"), f"{metodo.upper()} {caminho}"
            continue
        assert op.get("x-escopo-requerido"), f"{metodo.upper()} {caminho} sem escopo"
        assert f"`{op['x-escopo-requerido']}`" in op["description"]
        for status in ("401", "403", "422"):
            assert status in op["responses"], f"{metodo.upper()} {caminho} sem {status}"


def test_erros_usam_o_schema_unico(spec):
    # todo erro documentado aponta para ErroOut {code, message, hint, retryable}
    erro = spec["components"]["schemas"]["ErroOut"]
    assert set(erro["required"]) == {"code", "message", "hint", "retryable"}
    for caminho, metodo, op in _operacoes(spec):
        for status, resposta in op.get("responses", {}).items():
            if status.startswith(("4", "5")):
                conteudo = resposta["content"]["application/json"]
                assert conteudo["schema"]["$ref"].endswith("ErroOut"), (
                    f"{metodo.upper()} {caminho} {status} não usa ErroOut"
                )
                assert conteudo["examples"], f"{metodo.upper()} {caminho} {status} sem exemplo"


def test_conflito_de_slot_traz_alternativas_no_exemplo(spec):
    exemplos = spec["paths"]["/appointments"]["post"]["responses"]["409"]["content"][
        "application/json"
    ]["examples"]
    slot = exemplos["SLOT_INDISPONIVEL"]["value"]
    assert len(slot["alternativas"]) == 3
    assert {"inicio", "label_humano"} <= set(slot["alternativas"][0])


def test_cancelamento_documenta_propor_confirmar(spec):
    for caminho in ("/appointments/{appointment_id}/cancel", "/appointments/recorrentes/{series_id}/cancel"):
        exemplos = spec["paths"][caminho]["post"]["responses"]["409"]["content"][
            "application/json"
        ]["examples"]
        confirmacao = exemplos["CONFIRMACAO_NECESSARIA"]["value"]
        assert confirmacao["confirmation_token"]
        assert confirmacao["previa"]
        assert "CONFIRMACAO_EXPIRADA" in exemplos  # o token de 5 min também está documentado


def test_escritas_documentam_idempotency_key(spec):
    for caminho in ("/appointments", "/services", "/appointments/recorrentes"):
        params = spec["paths"][caminho]["post"].get("parameters", [])
        assert any(p["name"] == "Idempotency-Key" for p in params), caminho


def test_toda_operacao_tem_summary_e_exemplo_de_sucesso(spec):
    for caminho, metodo, op in _operacoes(spec):
        assert op.get("summary"), f"{metodo.upper()} {caminho} sem summary"


def test_artefato_versionado_esta_em_dia(spec):
    """docs/openapi.json é o contrato publicado — regenere com `make openapi`."""
    artefato = RAIZ_REPO / "docs" / "openapi.json"
    assert artefato.exists(), "rode `make openapi` e versione docs/openapi.json"
    assert json.loads(artefato.read_text(encoding="utf-8")) == spec, (
        "docs/openapi.json defasado — rode `make openapi` e inclua no commit"
    )
