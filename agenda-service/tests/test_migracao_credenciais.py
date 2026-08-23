# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""A migration 0003 tem que ser reversível e a RLS tem que sobreviver a ela.

O detalhe que quebra em silêncio: `force row level security`. A aplicação roda
como dona do banco; sem `force`, o dono ignora a própria política e o
isolamento entre organizações vira decoração.
"""

from sqlalchemy import text

from .conftest import integracao

pytestmark = integracao


def test_rls_esta_ligada_e_forcada_nas_tabelas_novas(banco_migrado):
    from app.sessao import engine

    with engine.connect() as conn:
        linhas = conn.execute(
            text(
                "select relname, relrowsecurity, relforcerowsecurity from pg_class "
                "where relname in ('agent_credentials','agent_audit_log')"
            )
        ).all()
    assert len(linhas) == 2
    for nome, habilitada, forcada in linhas:
        assert habilitada, f"{nome} sem RLS"
        assert forcada, f"{nome} sem FORCE — o dono do banco ignoraria a política"


def test_upgrade_downgrade_upgrade(banco_migrado):
    from alembic.config import Config

    from alembic import command
    from app.sessao import engine

    def existe(tabela: str) -> bool:
        with engine.connect() as conn:
            return bool(
                conn.execute(
                    text("select to_regclass(:t)"), {"t": f"public.{tabela}"}
                ).scalar()
            )

    cfg = Config("alembic.ini")
    assert existe("agent_credentials")

    command.downgrade(cfg, "0002")
    assert not existe("agent_credentials")
    assert not existe("agent_audit_log")

    command.upgrade(cfg, "head")
    assert existe("agent_credentials")


def test_credencial_de_uma_org_nao_e_visivel_da_outra(banco_migrado, org_id):
    """A última linha de defesa: mesmo que a aplicação esqueça o filtro, a RLS
    não deixa uma org enxergar credencial da outra."""
    import uuid

    from sqlalchemy import func, select

    from app.admin_cli import emitir
    from app.models import AgentCredential
    from app.sessao import SessionLocal, sessao_org

    outra = uuid.uuid4()
    emitir(org_id, "Minha", "operacao")
    emitir(outra, "Da vizinha", "operacao")

    with SessionLocal() as db:
        sessao_org(db, org_id)
        total = db.scalar(select(func.count()).select_from(AgentCredential))
        nomes = list(db.scalars(select(AgentCredential.nome)))
    assert total == 1
    assert nomes == ["Minha"]
