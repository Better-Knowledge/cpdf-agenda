# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Migrations reversíveis (`00` §4.6): upgrade → downgrade → upgrade,
num banco descartável para não interferir nos demais testes."""

import os

import sqlalchemy
from sqlalchemy import text

from .conftest import TEST_URL, integracao

pytestmark = integracao

MIG_DB = "agenda_migtest"


def test_upgrade_downgrade_upgrade(banco_migrado):
    from alembic.config import Config

    from alembic import command
    from app.config import settings

    admin = sqlalchemy.create_engine(TEST_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"drop database if exists {MIG_DB}"))
        conn.execute(text(f"create database {MIG_DB}"))

    url_mig = TEST_URL.rsplit("/", 1)[0] + f"/{MIG_DB}"
    os.environ["DATABASE_URL"] = url_mig
    settings.cache_clear()
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")

        eng = sqlalchemy.create_engine(url_mig)
        with eng.connect() as conn:
            sobraram = conn.execute(
                text(
                    "select tablename from pg_tables "
                    "where schemaname = 'public' and tablename <> 'alembic_version'"
                )
            ).fetchall()
        assert sobraram == []  # downgrade limpa tudo

        command.upgrade(cfg, "head")  # e o upgrade volta a funcionar
        eng.dispose()
    finally:
        os.environ["DATABASE_URL"] = TEST_URL
        settings.cache_clear()
        with admin.connect() as conn:
            conn.execute(text(f"drop database if exists {MIG_DB} with (force)"))
        admin.dispose()
