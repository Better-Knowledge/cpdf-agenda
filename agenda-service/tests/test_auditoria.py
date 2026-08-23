"""`00` §5.8 — a auditoria responde "quem fez isso, em nome de quem, e deu certo?".

O teste mais importante aqui é o negativo: a auditoria vive no
**agenda-service**, não no conector MCP. Se vivesse no conector, as ações do
agente de atendimento — o WhatsApp, a superfície que mais importa vigiar —
nunca apareceriam, porque elas não passam por MCP nenhum.
"""

import pytest
from sqlalchemy import select

from app.auth import credencial_atual
from app.main import app
from app.models import AgentAuditLog
from app.sessao import SessionLocal, sessao_org

from .conftest import credencial_falsa, integracao

pytestmark = integracao

TITULAR = "+5511999998888"


def _linhas(org_id) -> list[AgentAuditLog]:
    with SessionLocal() as db:
        sessao_org(db, org_id)
        return list(
            db.scalars(
                select(AgentAuditLog)
                .where(AgentAuditLog.org_id == org_id)
                .order_by(AgentAuditLog.id)
            )
        )


@pytest.fixture()
def limpo(client, catalogo, org_id):
    """O catálogo do fixture já gera escritas; zera para o teste ler só as suas."""
    from sqlalchemy import delete

    with SessionLocal() as db:
        sessao_org(db, org_id)
        db.execute(delete(AgentAuditLog).where(AgentAuditLog.org_id == org_id))
        db.commit()
    return catalogo


@pytest.fixture()
def como_atendimento(org_id):
    app.dependency_overrides[credencial_atual] = credencial_falsa(
        org_id, "atendimento", ator="agente", titular=TITULAR, nome="Bot do canal"
    )
    yield
    app.dependency_overrides.pop(credencial_atual, None)


def test_escrita_vira_linha_de_auditoria(client, limpo, org_id):
    client.post("/resources", json={"nome": "Sala 2", "tipo": "sala"})
    (linha,) = _linhas(org_id)
    assert linha.tool_name == "POST /resources"
    assert linha.mcp_server == "http"
    assert linha.resultado == "ok"
    assert linha.error_code is None
    assert linha.latencia_ms is not None


def test_leitura_bem_sucedida_nao_polui_o_log(client, limpo, org_id):
    """Um agente consultando /slots a cada mensagem geraria mais auditoria do
    que negócio, e o sinal sumiria no volume."""
    client.get("/services")
    client.get("/resources")
    client.get("/availability/rules")
    assert _linhas(org_id) == []


def test_recusa_por_escopo_e_auditada_com_o_motivo(client, limpo, org_id, como_atendimento):
    """A leitura recusada entra: negativa de autoridade é exatamente o evento
    que se quer ver depois."""
    client.get("/agenda/day?date=2026-08-27")
    (linha,) = _linhas(org_id)
    assert linha.resultado == "recusado"
    assert linha.error_code == "ESCOPO_INSUFICIENTE"
    assert linha.tool_name == "GET /agenda/day"


def test_a_acao_do_agente_de_atendimento_e_auditada(client, limpo, org_id, como_atendimento):
    """Aqui é onde a escolha de auditar no serviço, e não no MCP, aparece: o
    bot do canal não passa por conector nenhum, e mesmo assim fica no log."""
    from datetime import UTC, datetime, timedelta

    quando = (datetime.now(UTC) + timedelta(days=2)).replace(hour=13, minute=0, second=0, microsecond=0)
    while quando.weekday() > 4:
        quando += timedelta(days=1)
    client.post(
        "/appointments",
        json={
            "service_id": limpo["servico"]["id"],
            "inicio": quando.isoformat(),
            "cliente_nome": "Fulano",
            "cliente_telefone": TITULAR,
        },
    )
    (linha,) = _linhas(org_id)
    assert linha.tool_name == "POST /appointments"
    assert linha.actor == "Bot do canal"
    assert linha.titular == TITULAR  # em nome de quem, não só quem
    assert linha.resultado == "ok"


def test_o_conector_mcp_se_identifica(client, limpo, org_id):
    """Quando a chamada vem de uma tool, o log guarda o nome dela em vez da
    rota — é assim que o `agenda-admin-mcp` aparece no histórico."""
    client.post(
        "/resources",
        json={"nome": "Sala 3"},
        headers={"X-MCP-Server": "agenda-admin", "X-MCP-Tool": "agenda_admin_recurso_salvar"},
    )
    (linha,) = _linhas(org_id)
    assert linha.mcp_server == "agenda-admin"
    assert linha.tool_name == "agenda_admin_recurso_salvar"


def test_o_log_nunca_guarda_dado_do_cliente(client, limpo, org_id, como_atendimento):
    """`args_hash` cobre rota, query e Idempotency-Key — nunca o corpo, nunca
    um valor. Um log de auditoria que vaza é um vazamento a mais, não a menos."""
    client.get(f"/appointments/proximo?telefone={TITULAR}")  # 404, mas é leitura ok
    client.post(
        "/waitlist",
        json={
            "service_id": limpo["servico"]["id"],
            "cliente_nome": "Fulano de Tal",
            "cliente_telefone": TITULAR,
            "janela_inicio": "2026-09-01T12:00:00-03:00",
            "janela_fim": "2026-09-01T18:00:00-03:00",
        },
        headers={"Idempotency-Key": "chave-da-intencao"},
    )
    (linha,) = _linhas(org_id)
    texto = " ".join(str(v) for v in vars(linha).values())
    assert "Fulano de Tal" not in texto
    assert TITULAR not in texto.replace(str(linha.titular), "")  # titular é campo próprio
    assert len(linha.args_hash) == 32


def test_erro_de_negocio_entra_como_erro(client, limpo, org_id):
    import uuid

    client.patch(f"/resources/{uuid.uuid4()}", json={"nome": "x"})
    (linha,) = _linhas(org_id)
    assert linha.resultado == "erro"
    assert linha.error_code == "NAO_ENCONTRADO"


def test_falha_ao_gravar_auditoria_nao_derruba_a_requisicao(client, limpo, monkeypatch, org_id):
    """A auditoria é obrigação nossa, não do usuário: se o log quebrar, a
    escrita dele já aconteceu e a resposta é dele por direito. O que não pode
    é sumir em silêncio — daí o log.exception."""
    from app import auditoria

    def explodir(*_a, **_k):
        raise RuntimeError("banco de auditoria fora do ar")

    monkeypatch.setattr(auditoria, "AgentAuditLog", explodir)
    resposta = client.post("/resources", json={"nome": "Sala 4"})
    assert resposta.status_code == 201
    assert _linhas(org_id) == []
