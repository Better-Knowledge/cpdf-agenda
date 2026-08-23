"""Autenticação e escopos (fase 1 do conector — `00` §5.4).

Três formas de credencial, todas resolvendo para (org_id, escopos):
- JWT do Supabase Auth (`Authorization: Bearer <jwt>`) — UI e usuários humanos;
- API key de agente (`X-Agent-Key`) mapeada em AGENT_API_KEYS — fase 1 do MCP;
- `X-Org-Id` cru, aceito SOMENTE com APP_ENV=dev.

OAuth 2.1 completo (fase 2) chega com o `agenda-mcp` (PRD §14).
"""

from dataclasses import dataclass, field
from uuid import UUID

import jwt
from fastapi import Request

from .config import settings
from .errors import ApiError

ESCOPOS_PADRAO = {"agenda:read", "agenda:write", "agenda:cancel"}


@dataclass(frozen=True)
class Credencial:
    org_id: UUID
    escopos: frozenset[str] = field(default_factory=lambda: frozenset(ESCOPOS_PADRAO))
    ator: str = "humano"  # humano | agente


def _nao_autenticado(motivo: str) -> ApiError:
    return ApiError(
        code="NAO_AUTENTICADO",
        message=f"Credencial ausente ou inválida: {motivo}",
        hint="Envie `Authorization: Bearer <jwt do Supabase>` ou `X-Agent-Key`.",
        status_code=401,
    )


def credencial_atual(request: Request) -> Credencial:
    cfg = settings()

    # Service-to-service (agente/orquestrador): a chave autentica o SERVIÇO e a
    # org vem explícita no header — o inbound do canal já identifica a org.
    # ator="agente": ações irreversíveis seguem exigindo confirmação humana.
    service_key = request.headers.get("X-Service-Key")
    if service_key:
        if not cfg.agenda_service_key or service_key != cfg.agenda_service_key:
            raise _nao_autenticado("X-Service-Key desconhecida")
        org = request.headers.get("X-Org-Id")
        if not org:
            raise _nao_autenticado("X-Service-Key sem X-Org-Id")
        return Credencial(org_id=UUID(org), ator="agente")

    agent_key = request.headers.get("X-Agent-Key")
    if agent_key:
        org = cfg.agent_api_keys.get(agent_key)
        if not org:
            raise _nao_autenticado("X-Agent-Key desconhecida")
        return Credencial(org_id=UUID(org), ator="agente")

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.removeprefix("Bearer ")
        try:
            claims = jwt.decode(
                token, cfg.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated"
            )
        except jwt.PyJWTError as e:
            raise _nao_autenticado(f"JWT rejeitado ({e})") from e
        org = claims.get("org_id") or (claims.get("app_metadata") or {}).get("org_id")
        if not org:
            raise _nao_autenticado("JWT sem claim org_id")
        return Credencial(org_id=UUID(org))

    if cfg.dev_mode and (org := request.headers.get("X-Org-Id")):
        return Credencial(org_id=UUID(org))

    raise _nao_autenticado("nenhum header de credencial presente")


def exigir_escopo(cred: Credencial, escopo: str) -> None:
    if escopo not in cred.escopos:
        raise ApiError(
            code="ESCOPO_INSUFICIENTE",
            message=f"A credencial não tem o escopo '{escopo}'.",
            hint="Peça uma credencial com o escopo necessário — cancelamento exige agenda:cancel.",
            status_code=403,
        )
