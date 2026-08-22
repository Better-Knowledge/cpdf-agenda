import os
import uuid

import pytest
from cryptography.fernet import Fernet

ADMIN_URL = os.environ.get(
    "TEST_DATABASE_ADMIN_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
)
# Role não-superuser dono do banco — superuser ignora RLS mesmo com FORCE.
_HOSTPORT = ADMIN_URL.rsplit("@", 1)[1].rsplit("/", 1)[0]
TEST_URL = f"postgresql+psycopg://canal_app:canal_app@{_HOSTPORT}/canal_test"
os.environ["DATABASE_URL"] = TEST_URL
os.environ["APP_ENV"] = "dev"
os.environ.setdefault("CANAL_CRYPTO_KEY", Fernet.generate_key().decode())


def _garantir_banco() -> bool:
    import sqlalchemy
    from sqlalchemy import text

    try:
        eng = sqlalchemy.create_engine(
            ADMIN_URL, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 2}
        )
        with eng.connect() as conn:
            if not conn.execute(
                text("select 1 from pg_roles where rolname = 'canal_app'")
            ).scalar():
                conn.execute(text("create role canal_app login password 'canal_app'"))
            if not conn.execute(
                text("select 1 from pg_database where datname = 'canal_test'")
            ).scalar():
                conn.execute(text("create database canal_test owner canal_app"))
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


class TransporteFake:
    """Captura as chamadas HTTP que o driver faria à API de WhatsApp."""

    def __init__(self):
        self.requisicoes = []

    def cliente(self):
        import httpx

        def responder(request: httpx.Request) -> httpx.Response:
            self.requisicoes.append(request)
            # ids únicos, como nos drivers reais — (driver, driver_message_id) é unique
            serial = f"{uuid.uuid4().hex[:12]}"
            if "sendText" in str(request.url):  # evolution
                return httpx.Response(201, json={"key": {"id": f"EVO-{serial}"}})
            return httpx.Response(200, json={"messageId": f"ZAPI-{serial}"})  # zapi

        return httpx.Client(transport=httpx.MockTransport(responder))


@pytest.fixture()
def transporte(monkeypatch):
    """Redireciona obter_driver para instâncias com transporte HTTP falso."""
    from app.drivers.registry import DRIVERS

    fake = TransporteFake()

    def obter_driver_fake(nome, http=None):
        return DRIVERS[nome](http=fake.cliente())

    import app.routers.canal as canal_router
    import app.routers.webhooks as webhooks_router

    monkeypatch.setattr(canal_router, "obter_driver", obter_driver_fake)
    monkeypatch.setattr(webhooks_router, "obter_driver", obter_driver_fake)
    return fake


@pytest.fixture()
def instancia(org_id) -> str:
    # unique (driver, instancia) é global — cada teste usa a sua
    return f"inst-{org_id.hex[:10]}"


@pytest.fixture()
def canal_configurado(client, transporte, instancia):
    """Configura driver + template de lembrete para a org do teste."""

    credenciais = {
        "evolution": {"server_url": "http://evolution.local", "instancia": instancia, "apikey": "k"},
        "zapi": {"instancia": instancia, "token": "t", "client_token": "ct"},
    }

    def configurar(driver: str = "evolution"):
        resposta = client.post(
            "/canal/config",
            json={
                "driver": driver,
                "numero": "+5511900000000",
                "instancia": instancia,
                "credenciais": credenciais[driver],
                "confirmo_numero_dedicado": True,
            },
        )
        assert resposta.status_code == 201, resposta.text
        # o token de webhook aparece uma única vez, na resposta da config
        transporte.webhook_url = resposta.json()["webhook_url"]
        client.post(
            "/canal/templates",
            json={
                "nome": "lembrete_24h",
                "corpo": "Oi {{nome}}! Lembrete: {{servico}} {{data_hora}}. Responda SAIR para não receber mais.",
            },
        )
        return transporte

    return configurar
