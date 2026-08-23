# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Segredos de terceiros cifrados na aplicação (write-only na API).

Aqui vivem os tokens OAuth do Google (RF-12). O banco guarda o texto
cifrado; nem a UI nem o /docs jamais devolvem o valor — o que a tela vê é
"conectado desde tal dia", nunca a credencial.

Mesma construção do `canal-service`, com chave própria: comprometer um
serviço não deve entregar os segredos do outro.
"""

import json
from typing import Any

from cryptography.fernet import Fernet

from .config import settings
from .errors import ApiError


def _fernet() -> Fernet:
    chave = settings().agenda_crypto_key
    try:
        return Fernet(chave.encode())
    except Exception as e:
        raise ApiError(
            code="CRYPTO_NAO_CONFIGURADO",
            message="AGENDA_CRYPTO_KEY ausente ou inválida — segredos não podem ser gravados.",
            hint="Gere uma chave Fernet e configure no .env do VPS (ver .env.example).",
            status_code=500,
        ) from e


def cifrar(segredo: dict[str, Any]) -> dict[str, str]:
    return {"cifrado": _fernet().encrypt(json.dumps(segredo).encode()).decode()}


def decifrar(guardado: dict[str, Any]) -> dict[str, Any]:
    return json.loads(_fernet().decrypt(guardado["cifrado"].encode()))
