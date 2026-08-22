"""Mesmo contrato de erro do programa: {code, message, hint, retryable}."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    status_code = 400

    def __init__(
        self,
        code: str,
        message: str,
        hint: str = "",
        *,
        retryable: bool = False,
        status_code: int | None = None,
        extra: dict[str, Any] | None = None,
    ):
        self.code = code
        self.message = message
        self.hint = hint
        self.retryable = retryable
        if status_code is not None:
            self.status_code = status_code
        self.extra = extra or {}

    def payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
            "retryable": self.retryable,
            **self.extra,
        }


def instalar_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.payload())

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        detalhes = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        return JSONResponse(
            status_code=422,
            content={
                "code": "PAYLOAD_INVALIDO",
                "message": f"Payload inválido: {detalhes}",
                "hint": "Corrija os campos apontados e repita a chamada.",
                "retryable": False,
            },
        )
