from fastapi import APIRouter
from sqlalchemy import text

from ..db import engine

router = APIRouter(tags=["operacao"])


@router.get("/health", summary="Liveness/readiness do serviço")
def health() -> dict:
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        banco = "ok"
    except Exception:
        banco = "fora"
    return {"status": "ok" if banco == "ok" else "degradado", "banco": banco}
