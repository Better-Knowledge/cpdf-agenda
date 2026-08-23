# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""RLS ativa e testada com dois org_id diferentes (`00` §4.6).

A consulta é feita SEM filtro de org na query — só o GUC muda. Quem
segura a linha é a política no banco, não a aplicação.
"""

import uuid

from sqlalchemy import select

from .conftest import integracao

pytestmark = integracao


def test_org_nao_enxerga_dados_da_outra(banco_migrado):
    from app.db import SessionLocal, sessao_org
    from app.models import Service

    org_a, org_b = uuid.uuid4(), uuid.uuid4()

    with SessionLocal() as db:
        sessao_org(db, org_a)
        db.add(Service(org_id=org_a, nome="Corte", duracao_min=30))
        db.commit()

    with SessionLocal() as db:
        sessao_org(db, org_b)
        visiveis = db.scalars(select(Service)).all()  # sem WHERE de org, de propósito
        assert visiveis == []

    with SessionLocal() as db:
        sessao_org(db, org_a)
        assert len(db.scalars(select(Service)).all()) == 1


def test_sessao_sem_org_nao_enxerga_nada(banco_migrado):
    """Fail-closed: GUC vazio (conexão recém-saída do pool) → zero linhas."""
    from app.db import SessionLocal
    from app.models import Service

    with SessionLocal() as db:
        assert db.scalars(select(Service)).all() == []


def test_escrita_para_outra_org_e_barrada(banco_migrado):
    from sqlalchemy.exc import ProgrammingError

    from app.db import SessionLocal, sessao_org
    from app.models import Service

    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    with SessionLocal() as db:
        sessao_org(db, org_a)
        db.add(Service(org_id=org_b, nome="Invasão", duracao_min=30))
        try:
            db.commit()
            raise AssertionError("escrita cross-org deveria ter sido barrada pela RLS")
        except ProgrammingError:
            db.rollback()
