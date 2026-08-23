# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Padrão propor → confirmar (`00` §5.7) para ações irreversíveis.

Cancelamento disparado por agente exige confirmação humana. Sem elicitation
(que chega com o agenda-mcp), o fluxo é: a primeira chamada devolve uma
prévia com `confirmation_token`; a segunda, com o token, executa. Token
assinado (HMAC), sem estado no banco, expira em 5 minutos.
"""

import base64
import hashlib
import hmac
import json
from uuid import UUID

from .config import settings
from .errors import ApiError
from .tempo import agora_utc

VALIDADE_SEGUNDOS = 300


def _assinar(corpo: bytes) -> str:
    chave = settings().supabase_jwt_secret.encode() or b"dev"
    return hmac.new(chave, corpo, hashlib.sha256).hexdigest()


def gerar_token(acao: str, alvo_id: UUID) -> str:
    corpo = json.dumps(
        {"acao": acao, "id": str(alvo_id), "exp": int(agora_utc().timestamp()) + VALIDADE_SEGUNDOS}
    ).encode()
    return base64.urlsafe_b64encode(corpo).decode() + "." + _assinar(corpo)


def validar_token(token: str, acao: str, alvo_id: UUID) -> None:
    try:
        payload_b64, assinatura = token.split(".")
        corpo = base64.urlsafe_b64decode(payload_b64)
        assert hmac.compare_digest(assinatura, _assinar(corpo))
        dados = json.loads(corpo)
        assert dados["acao"] == acao and dados["id"] == str(alvo_id)
        expirado = dados["exp"] < agora_utc().timestamp()
    except Exception as e:
        raise ApiError(
            code="CONFIRMACAO_INVALIDA",
            message="confirmation_token inválido para esta ação.",
            hint="Refaça a chamada sem token para receber uma nova prévia e um token novo.",
            status_code=409,
        ) from e
    if expirado:
        raise ApiError(
            code="CONFIRMACAO_EXPIRADA",
            message="O confirmation_token expirou (validade de 5 minutos).",
            hint="Refaça a chamada sem token, confirme com o humano e use o token novo.",
            status_code=409,
        )
