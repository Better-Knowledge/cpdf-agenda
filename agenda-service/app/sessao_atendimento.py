# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Token de sessão de atendimento (RF-19) — a prova de que o agente fala por UM cliente.

**O problema que ele resolve.** O agente do canal precisa agir em nome do
cliente que escreveu. Até aqui ele se identificava com uma chave de serviço e
dizia, no próprio pedido, para quem estava trabalhando. Isso não é fronteira:
é o ator restringido declarando a própria restrição — se ele (ou quem tomar a
chave dele) trocar o telefone, alcança o compromisso de qualquer pessoa.

**Onde o endereço é provado.** Existe exatamente um ponto no sistema em que
sabemos, por evidência e não por afirmação, de quem é a mensagem: dentro do
`canal-service`, depois de `hmac.compare_digest(config.webhook_token, token)`.
É lá que este token é cunhado, e é por isso que o `titular` viaja assinado em
vez de viajar num header.

**Formato.** `ats_<payload base64url>.<hmac sha256 hex>`, autocontido, sem
estado no banco — um agente que reinicia não perde sessão, e revogar não é
necessário porque a validade é curta (30 min, o tempo de uma conversa).

**Domínio de assinatura separado.** `confirmacao.py` também assina com HMAC.
Sem o prefixo de domínio abaixo, um token de sessão válido poderia ser
apresentado como `confirmation_token` (ou o contrário) sempre que os dois
segredos coincidissem — e coincidir é exatamente o que acontece quando alguém
reusa `SUPABASE_JWT_SECRET` por conveniência. O prefixo torna a colisão
impossível por construção, não por disciplina.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
from dataclasses import dataclass
from uuid import UUID

from .auth import PAPEIS
from .config import settings
from .enderecos import normalizar
from .errors import ApiError
from .tempo import agora_utc

log = logging.getLogger("agenda.sessao_atendimento")

PREFIXO = "ats_"
DOMINIO = b"cpdf.sessao-atendimento.v1"
VALIDADE_SEGUNDOS = 1800  # 30 min: a duração de uma conversa, não de um turno

# Teto duro. Os escopos vêm assinados, mas um token de atendimento nunca
# ultrapassa o papel 'atendimento' — nem se alguém cunhar reivindicando mais.
TETO = PAPEIS["atendimento"]


@dataclass(frozen=True)
class Sessao:
    org_id: UUID
    titular: str
    escopos: frozenset[str]
    jti: str


def _chave() -> bytes:
    cfg = settings()
    if segredo := cfg.sessao_atendimento_secret:
        return segredo.encode()
    if not cfg.dev_mode:
        raise RuntimeError(
            "SESSAO_ATENDIMENTO_SECRET vazio em produção: sem ele o token de "
            "atendimento seria assinado com um segredo público e qualquer um "
            "poderia falar por qualquer cliente."
        )
    log.warning("SESSAO_ATENDIMENTO_SECRET vazio — usando segredo de desenvolvimento")
    return b"dev-sessao-atendimento"


def _assinar(corpo: bytes) -> str:
    return hmac.new(_chave(), DOMINIO + b"|" + corpo, hashlib.sha256).hexdigest()


def emitir(org_id: UUID, titular: str, escopos: frozenset[str] | None = None) -> str:
    """Cunha o token. Chamado pelo canal-service — ver a cópia gêmea em
    `canal-service/app/sessao_atendimento.py`, que precisa gerar exatamente
    este formato (o teste de vetor fixo, dos dois lados, é o que garante)."""
    corpo = json.dumps(
        {
            "org": str(org_id),
            "tit": normalizar(titular),
            "esc": sorted(escopos or TETO),
            "jti": secrets.token_urlsafe(8),
            "exp": int(agora_utc().timestamp()) + VALIDADE_SEGUNDOS,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    payload = base64.urlsafe_b64encode(corpo).decode().rstrip("=")
    return f"{PREFIXO}{payload}.{_assinar(corpo)}"


def _recusar(motivo: str) -> ApiError:
    return ApiError(
        code="SESSAO_INVALIDA",
        message=f"Token de sessão de atendimento inválido: {motivo}",
        hint=(
            "O token é cunhado pelo canal a cada mensagem do cliente e vale 30 "
            "minutos. Aguarde a próxima mensagem em vez de reaproveitar o antigo."
        ),
        status_code=401,
    )


def validar(token: str) -> Sessao:
    try:
        payload, assinatura = token.removeprefix(PREFIXO).split(".")
        corpo = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    except Exception as e:
        raise _recusar("formato irreconhecível") from e
    if not hmac.compare_digest(assinatura, _assinar(corpo)):
        raise _recusar("assinatura não confere")
    try:
        dados = json.loads(corpo)
        org_id, titular = UUID(dados["org"]), normalizar(dados["tit"])
        escopos = frozenset(dados["esc"]) & TETO
        expira = int(dados["exp"])
    except Exception as e:
        raise _recusar("conteúdo malformado") from e
    if not titular:
        raise _recusar("sem titular")
    if expira < agora_utc().timestamp():
        raise _recusar("expirado")
    return Sessao(org_id=org_id, titular=titular, escopos=escopos, jti=dados["jti"])
