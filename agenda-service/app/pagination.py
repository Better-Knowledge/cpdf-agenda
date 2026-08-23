# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Cursor opaco para listagens (`limit`/`cursor` — convenção do programa).

O cursor codifica (created_at, id) do último item; estável sob inserções
concorrentes, ao contrário de offset.
"""

import base64
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from .errors import ApiError


def codificar_cursor(created_at: datetime, id_: UUID | int) -> str:
    bruto = json.dumps({"c": created_at.isoformat(), "i": str(id_)}).encode()
    return base64.urlsafe_b64encode(bruto).decode()


def decodificar_cursor(cursor: str) -> dict[str, Any]:
    try:
        dados = json.loads(base64.urlsafe_b64decode(cursor))
        return {"created_at": datetime.fromisoformat(dados["c"]), "id": dados["i"]}
    except Exception as e:
        raise ApiError(
            code="CURSOR_INVALIDO",
            message="O cursor de paginação não foi reconhecido.",
            hint="Use exatamente o next_cursor devolvido pela página anterior.",
        ) from e
