# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""O `state` do OAuth do Google (RF-12), assinado e com validade curta.

O `state` é a única coisa que atravessa o navegador entre "quero conectar" e
"o Google respondeu". Ele diz por qual organização e para qual recurso a
conexão é — e chega de volta numa rota **pública**, porque o Google redireciona
o navegador, não chama a API com credencial.

Por isso ele é assinado: sem assinatura, qualquer pessoa acertaria a rota de
callback com um `state` inventado e ligaria a própria conta do Google ao
recurso de outra organização. Domínio próprio na assinatura (`cpdf.oauth-google.v1`)
para que um token de sessão de atendimento ou um `confirmation_token` jamais
sejam aceitos aqui — e vice-versa.
"""

import base64
import hashlib
import hmac
import json
from uuid import UUID

from .config import settings
from .errors import ApiError
from .tempo import agora_utc

DOMINIO = b"cpdf.oauth-google.v1"
VALIDADE_SEGUNDOS = 600  # o tempo de escolher a conta e aceitar a tela do Google


def _chave() -> bytes:
    cfg = settings()
    chave = cfg.supabase_jwt_secret.encode()
    if not chave:
        if not cfg.dev_mode:
            raise ApiError(
                code="OAUTH_NAO_CONFIGURADO",
                message="Sem segredo de assinatura, o state do OAuth não pode ser emitido.",
                hint="Configure SUPABASE_JWT_SECRET no .env do VPS.",
                status_code=500,
            )
        return b"dev"
    return chave


def _assinar(corpo: bytes) -> str:
    return hmac.new(_chave(), DOMINIO + b"|" + corpo, hashlib.sha256).hexdigest()


def emitir(org_id: UUID, resource_id: UUID) -> str:
    corpo = json.dumps(
        {
            "org": str(org_id),
            "res": str(resource_id),
            "exp": int(agora_utc().timestamp()) + VALIDADE_SEGUNDOS,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(corpo).decode().rstrip("=") + "." + _assinar(corpo)


def validar(state: str) -> tuple[UUID, UUID]:
    erro = ApiError(
        code="OAUTH_ESTADO_INVALIDO",
        message="O state do OAuth é inválido ou expirou.",
        hint="Recomece a conexão pela tela de Integrações — o link vale 10 minutos.",
        status_code=400,
    )
    try:
        payload_b64, assinatura = state.split(".")
        corpo = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
        if not hmac.compare_digest(assinatura, _assinar(corpo)):
            raise ValueError("assinatura")
        dados = json.loads(corpo)
        expirado = dados["exp"] < agora_utc().timestamp()
        org, recurso = UUID(dados["org"]), UUID(dados["res"])
    except ApiError:
        raise
    except Exception as e:
        raise erro from e
    if expirado:
        raise erro
    return org, recurso
