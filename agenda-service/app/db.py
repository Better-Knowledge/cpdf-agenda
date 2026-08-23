# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Dependência de sessão do FastAPI — a sessão em si vive em `sessao.py`.

A separação existe porque `auth.py` precisa de uma sessão para resolver a
credencial no banco, e este módulo importa `auth.py`. Reexportamos os nomes
antigos para não quebrar os call-sites existentes.
"""

from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from .auth import Credencial, credencial_atual
from .sessao import SessionLocal, engine, sessao_org, sessao_worker

__all__ = ["SessionLocal", "engine", "sessao_org", "sessao_worker", "get_db"]


def get_db(cred: Credencial = Depends(credencial_atual)) -> Generator[Session, None, None]:
    with SessionLocal() as db:
        sessao_org(db, cred.org_id)
        yield db
