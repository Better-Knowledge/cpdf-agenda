"""Idempotência de escrita (convenção do programa, `00` §4.2).

Uso nos routers:

    resposta = idem.buscar(db, cred.org_id, request)
    if resposta is not None:
        return resposta
    ...executa a escrita...
    idem.gravar(db, cred.org_id, request, corpo, status_code)

Repetir a chamada com a mesma Idempotency-Key devolve a mesma resposta,
sem duplicar efeito. Sem o header, a escrita segue normal (o conector MCP
sempre envia).
"""

from typing import Any
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import IdempotencyKey


def _chave(request: Request) -> str | None:
    return request.headers.get("Idempotency-Key")


def _endpoint(request: Request) -> str:
    return f"{request.method} {request.url.path}"


def buscar(db: Session, org_id: UUID, request: Request) -> JSONResponse | None:
    chave = _chave(request)
    if not chave:
        return None
    linha = db.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.org_id == org_id,
            IdempotencyKey.chave == chave,
            IdempotencyKey.endpoint == _endpoint(request),
        )
    )
    if linha is None:
        return None
    return JSONResponse(status_code=linha.status_code, content=linha.resposta)


def gravar(
    db: Session, org_id: UUID, request: Request, resposta: dict[str, Any], status_code: int = 200
) -> None:
    chave = _chave(request)
    if not chave:
        return
    db.add(
        IdempotencyKey(
            org_id=org_id,
            chave=chave,
            endpoint=_endpoint(request),
            resposta=resposta,
            status_code=status_code,
        )
    )
