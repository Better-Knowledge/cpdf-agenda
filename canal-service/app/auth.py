# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""O canal só aceita chamadas dos serviços do programa (PRD §11):
credencial service-to-service + org explícita. Nunca do navegador.
Webhooks inbound são a exceção — autenticados pelo segredo do driver.
"""

from dataclasses import dataclass
from uuid import UUID

from fastapi import Request

from .config import settings
from .errors import ApiError


@dataclass(frozen=True)
class Chamador:
    org_id: UUID


def chamador_atual(request: Request) -> Chamador:
    cfg = settings()
    chave = request.headers.get("X-Service-Key", "")
    org = request.headers.get("X-Org-Id", "")
    autorizado = (cfg.canal_service_key and chave == cfg.canal_service_key) or (
        cfg.dev_mode and org
    )
    if not autorizado or not org:
        raise ApiError(
            code="NAO_AUTENTICADO",
            message="Chamada sem credencial service-to-service válida.",
            hint="Envie X-Service-Key (credencial do serviço) e X-Org-Id.",
            status_code=401,
        )
    return Chamador(org_id=UUID(org))
