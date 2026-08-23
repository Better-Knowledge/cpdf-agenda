# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

from fastapi import APIRouter
from sqlalchemy import text

from ..db import engine

router = APIRouter(tags=["saúde"])


@router.get(
    "/health",
    summary="Liveness/readiness do serviço",
    description="Sem autenticação. `banco: fora` indica degradação — a API responde, o Postgres não.",
)
def health() -> dict:
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        banco = "ok"
    except Exception:
        banco = "fora"
    return {"status": "ok" if banco == "ok" else "degradado", "banco": banco}
