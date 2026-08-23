# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

from collections.abc import Generator
from uuid import UUID

from fastapi import Depends
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .auth import Chamador, chamador_atual
from .config import settings

engine = create_engine(settings().database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@event.listens_for(SessionLocal, "after_begin")
def _aplicar_contexto_rls(session: Session, _transaction, connection) -> None:
    """GUC transaction-local reaplicado a cada transação — commit/rollback o
    apagam, então conexão nunca volta ao pool com org de outra requisição
    (mesmo padrão do agenda-service/app/db.py)."""
    org = session.info.get("org_id")
    if org is not None:
        connection.exec_driver_sql("select set_config('app.org_id', %s, true)", (str(org),))
    if session.info.get("worker"):
        connection.exec_driver_sql("select set_config('app.role', 'worker', true)")


def sessao_org(db: Session, org_id: UUID) -> None:
    db.info["org_id"] = org_id


def sessao_worker(db: Session) -> None:
    """Webhooks inbound resolvem a org pelo payload — a varredura de configs
    cruza orgs, só o backend seta este GUC."""
    db.info["worker"] = True


def get_db(chamador: Chamador = Depends(chamador_atual)) -> Generator[Session, None, None]:
    with SessionLocal() as db:
        sessao_org(db, chamador.org_id)
        yield db
