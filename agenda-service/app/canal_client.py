"""Único caminho para o WhatsApp: o canal-service (`00` §4.8).

Nenhum código deste serviço fala com API de WhatsApp — mensagem ativa é
sempre template, e quem aplica a regra (e o opt-out) é o canal.
"""

from typing import Any
from uuid import UUID

import httpx

from .config import settings


class CanalIndisponivel(Exception):
    pass


def enviar_template(
    *,
    org_id: UUID,
    destinatario: str,
    template_nome: str,
    variaveis: dict[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    cfg = settings()
    try:
        resposta = httpx.post(
            f"{cfg.canal_service_url}/canal/enviar",
            json={
                "destinatario": destinatario,
                "tipo": "template",
                "template_nome": template_nome,
                "variaveis": variaveis,
            },
            headers={
                "X-Service-Key": cfg.canal_service_key,
                "X-Org-Id": str(org_id),
                "Idempotency-Key": idempotency_key,
            },
            timeout=15,
        )
    except httpx.HTTPError as e:
        raise CanalIndisponivel(str(e)) from e
    if resposta.status_code >= 500:
        raise CanalIndisponivel(f"canal respondeu {resposta.status_code}")
    return {"status_code": resposta.status_code, **resposta.json()}
