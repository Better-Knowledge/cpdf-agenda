"""Migration reversível é regra do repo: upgrade → downgrade → upgrade.

O caso interessante aqui é a 0002: a limpeza do downgrade acontece numa
tabela com RLS FORCE, que se aplica até ao dono. Se a política não for
suspensa, o DELETE não vê linha nenhuma e a constraint volta quebrada.
"""

import uuid

from .conftest import integracao

pytestmark = integracao


def _config_telegram(org_id: uuid.UUID) -> None:
    from app import crypto
    from app.db import SessionLocal, sessao_org
    from app.models import ChannelConfig

    with SessionLocal() as db:
        sessao_org(db, org_id)
        db.add(
            ChannelConfig(
                org_id=org_id,
                driver="telegram",
                credenciais=crypto.cifrar({"bot_token": "123:ABC"}),
                numero="@bot_da_aula",
                instancia=f"tg-{org_id.hex[:8]}",
                webhook_token="segredo",
            )
        )
        db.commit()


def test_downgrade_limpa_telegram_apesar_do_rls(banco_migrado, org_id):
    from alembic.config import Config
    from sqlalchemy import text

    from alembic import command
    from app.db import engine

    _config_telegram(org_id)

    cfg = Config("alembic.ini")
    command.downgrade(cfg, "0001")

    with engine.connect() as conn:
        (definicao,) = conn.execute(
            text(
                "select pg_get_constraintdef(oid) from pg_constraint "
                "where conname = 'driver_valido'"
            )
        ).one()
    assert "telegram" not in definicao  # constraint voltou ao estado anterior

    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        (definicao,) = conn.execute(
            text(
                "select pg_get_constraintdef(oid) from pg_constraint "
                "where conname = 'driver_valido'"
            )
        ).one()
        # e a RLS foi devolvida como estava (enable + force)
        (habilitada, forcada) = conn.execute(
            text("select relrowsecurity, relforcerowsecurity from pg_class where relname = 'channel_configs'")
        ).one()
    assert "telegram" in definicao
    assert habilitada and forcada
