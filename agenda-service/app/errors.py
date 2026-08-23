# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Contrato único de erro do programa: {code, message, hint, retryable}.

O `hint` é escrito para o agente ler e agir — quando possível, já traz a
saída (ex.: as 3 alternativas de horário) no próprio payload.
"""

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


class NaoEncontrado(ApiError):
    status_code = 404

    def __init__(self, recurso: str, id_: str):
        super().__init__(
            code="NAO_ENCONTRADO",
            message=f"{recurso} {id_} não existe nesta organização.",
            hint="Confira o id — liste o recurso correspondente para obter ids válidos.",
        )


def instalar_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        # A auditoria precisa do `code` para responder "por que foi recusado?".
        # O corpo da resposta já saiu do alcance do middleware quando ele roda.
        request.state.error_code = exc.code
        return JSONResponse(status_code=exc.status_code, content=exc.payload())

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        request.state.error_code = "PAYLOAD_INVALIDO"
        detalhes = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        return JSONResponse(
            status_code=422,
            content={
                "code": "PAYLOAD_INVALIDO",
                "message": f"Payload inválido: {detalhes}",
                "hint": "Corrija os campos apontados e repita a chamada com os mesmos dados.",
                "retryable": False,
            },
        )
