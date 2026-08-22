"""Credenciais de driver cifradas na aplicação (write-only na API).

Nunca em log, nunca em resposta — a UI (T-09) só vê status da conexão.
"""

import json
from typing import Any

from cryptography.fernet import Fernet

from .config import settings
from .errors import ApiError


def _fernet() -> Fernet:
    chave = settings().canal_crypto_key
    try:
        return Fernet(chave.encode())
    except Exception as e:
        raise ApiError(
            code="CRYPTO_NAO_CONFIGURADO",
            message="CANAL_CRYPTO_KEY ausente ou inválida — credenciais não podem ser gravadas.",
            hint="Gere uma chave Fernet e configure no .env do VPS (ver .env.example).",
            status_code=500,
        ) from e


def cifrar(credenciais: dict[str, Any]) -> dict[str, str]:
    return {"cifrado": _fernet().encrypt(json.dumps(credenciais).encode()).decode()}


def decifrar(guardado: dict[str, Any]) -> dict[str, Any]:
    return json.loads(_fernet().decrypt(guardado["cifrado"].encode()))
