# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Cunhagem do token de sessão de atendimento (RF-19).

**Gêmeo de `agenda-service/app/sessao_atendimento.py`** — aquele é o
canônico, com a explicação inteira; este só emite. A duplicação é
deliberada: os dois serviços são deployables separados, sem biblioteca
compartilhada, e um pacote comum para 40 linhas custaria mais do que um
teste de vetor fixo dos dois lados (`test_sessao_atendimento.py` aqui e lá)
— que é o que de fato impede o formato de divergir.

Por que aqui e não na agenda: este é o único lugar do sistema em que o
endereço do cliente é **provado** e não apenas afirmado — logo depois de
`hmac.compare_digest(config.webhook_token, token)` em `routers/webhooks.py`.
Um titular escolhido em qualquer outro ponto seria o ator restringido
declarando a própria restrição.
"""

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
from datetime import UTC, datetime
from uuid import UUID

from .config import settings

log = logging.getLogger("canal.sessao_atendimento")

PREFIXO = "ats_"
DOMINIO = b"cpdf.sessao-atendimento.v1"
VALIDADE_SEGUNDOS = 1800
ESCOPOS_ATENDIMENTO = ("agenda:read", "agenda:write")

_NAO_DIGITO = re.compile(r"\D")
_ESQUEMA = re.compile(r"^([a-z][a-z0-9+.-]*):(.*)$", re.IGNORECASE)


def normalizar(endereco: str | None) -> str:
    """Mesma regra de `agenda-service/app/enderecos.py`. Os drivers já
    produzem a forma canônica (`+digitos`, `tg:<chat_id>`), então aqui isto é
    quase sempre identidade — o ponto é que o titular assinado e a coluna
    `cliente_telefone` cheguem à comparação pela mesma régua."""
    bruto = (endereco or "").strip()
    if not bruto:
        return ""
    if m := _ESQUEMA.match(bruto):
        return f"{m.group(1).lower()}:{m.group(2).strip()}"
    digitos = _NAO_DIGITO.sub("", bruto)
    return f"+{digitos}" if digitos else bruto


def _chave() -> bytes:
    cfg = settings()
    if segredo := cfg.sessao_atendimento_secret:
        return segredo.encode()
    if not cfg.dev_mode:
        raise RuntimeError(
            "SESSAO_ATENDIMENTO_SECRET vazio em produção: o token de atendimento "
            "seria assinado com um segredo público e qualquer um poderia falar "
            "por qualquer cliente."
        )
    log.warning("SESSAO_ATENDIMENTO_SECRET vazio — usando segredo de desenvolvimento")
    return b"dev-sessao-atendimento"


def emitir(org_id: UUID, titular: str) -> str:
    corpo = json.dumps(
        {
            "org": str(org_id),
            "tit": normalizar(titular),
            "esc": sorted(ESCOPOS_ATENDIMENTO),
            "jti": secrets.token_urlsafe(8),
            "exp": int(datetime.now(UTC).timestamp()) + VALIDADE_SEGUNDOS,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    assinatura = hmac.new(_chave(), DOMINIO + b"|" + corpo, hashlib.sha256).hexdigest()
    payload = base64.urlsafe_b64encode(corpo).decode().rstrip("=")
    return f"{PREFIXO}{payload}.{assinatura}"
