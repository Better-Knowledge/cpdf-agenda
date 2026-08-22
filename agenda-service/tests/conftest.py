"""Fixtures dos testes.

Unidade (motor de slots, tempo) roda sem banco. Integração exige um
Postgres: `make dev-db` sobe um local, ou aponte TEST_DATABASE_URL.
Os testes de integração são pulados (skip) se o banco não responder.
"""

import os
import uuid

import pytest

# URL do superusuário do Postgres de teste (cria banco e role de app)
ADMIN_URL = os.environ.get(
    "TEST_DATABASE_ADMIN_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
)
# A aplicação roda como role NÃO-superuser dono do banco — como no Supabase.
# Superuser ignora RLS mesmo com FORCE; testar com ele seria teatro.
_HOSTPORT = ADMIN_URL.rsplit("@", 1)[1].rsplit("/", 1)[0]
TEST_URL = f"postgresql+psycopg://agenda_app:agenda_app@{_HOSTPORT}/agenda_test"
# Antes de qualquer import de app.* — settings lê o ambiente uma única vez.
os.environ["DATABASE_URL"] = TEST_URL
os.environ["APP_ENV"] = "dev"
os.environ.setdefault("SUPABASE_JWT_SECRET", "segredo-de-teste")
os.environ.setdefault("ANTECEDENCIA_MINIMA_MIN", "0")


def _garantir_banco() -> bool:
    import sqlalchemy
    from sqlalchemy import text

    try:
        eng = sqlalchemy.create_engine(
            ADMIN_URL, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 2}
        )
        with eng.connect() as conn:
            if not conn.execute(
                text("select 1 from pg_roles where rolname = 'agenda_app'")
            ).scalar():
                conn.execute(
                    text("create role agenda_app login password 'agenda_app' createdb")
                )
            if not conn.execute(
                text("select 1 from pg_database where datname = 'agenda_test'")
            ).scalar():
                conn.execute(text("create database agenda_test owner agenda_app"))
        return True
    except Exception:
        return False


BANCO_OK = _garantir_banco()
integracao = pytest.mark.skipif(not BANCO_OK, reason="Postgres de teste indisponível")


@pytest.fixture(scope="session")
def banco_migrado():
    if not BANCO_OK:
        pytest.skip("Postgres de teste indisponível")
    from alembic.config import Config

    from alembic import command

    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture()
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture()
def client(banco_migrado, org_id):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, headers={"X-Org-Id": str(org_id)}) as c:
        yield c


@pytest.fixture()
def catalogo(client):
    """Serviço de 60 min (buffer 0/10) + recurso + grade seg–sex 9h–18h."""
    recurso = client.post("/resources", json={"nome": "Sala 1", "tipo": "sala"}).json()
    servico = client.post(
        "/services",
        json={
            "nome": "Corte",
            "duracao_min": 60,
            "preco": "80.00",
            "buffer_depois_min": 10,
            "resource_ids": [recurso["id"]],
        },
    ).json()
    for dia in range(5):
        client.post(
            "/availability/rules",
            json={
                "resource_id": recurso["id"],
                "dia_semana": dia,
                "hora_inicio": "09:00",
                "hora_fim": "18:00",
            },
        )
    return {"servico": servico, "recurso": recurso}
