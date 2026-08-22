from collections.abc import Generator
from uuid import UUID

from fastapi import Depends
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .auth import Credencial, credencial_atual
from .config import settings

engine = create_engine(settings().database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@event.listens_for(SessionLocal, "after_begin")
def _aplicar_contexto_rls(session: Session, _transaction, connection) -> None:
    """Reaplica o contexto de org/worker no início de CADA transação, como GUC
    transaction-local (set_config ..., true). As políticas RLS leem esses GUCs
    (app.current_org_id()/app.is_worker() — migration 0001).

    Transaction-local por design: commit ou rollback apagam o GUC, então uma
    conexão nunca volta ao pool carregando o org da requisição anterior —
    fail-closed sem limpeza manual.
    """
    org = session.info.get("org_id")
    if org is not None:
        connection.exec_driver_sql("select set_config('app.org_id', %s, true)", (str(org),))
    if session.info.get("worker"):
        connection.exec_driver_sql("select set_config('app.role', 'worker', true)")


def sessao_org(db: Session, org_id: UUID) -> None:
    """Fixa o org da sessão. A aplicação também filtra por org_id em toda
    query; a RLS é a última linha de defesa, não a única."""
    db.info["org_id"] = org_id


def sessao_worker(db: Session) -> None:
    """Modo worker (jobs): a política RLS libera todas as orgs para este GUC —
    só o backend consegue setá-lo (equivalente explícito do service_role)."""
    db.info["worker"] = True


def get_db(cred: Credencial = Depends(credencial_atual)) -> Generator[Session, None, None]:
    with SessionLocal() as db:
        sessao_org(db, cred.org_id)
        yield db
