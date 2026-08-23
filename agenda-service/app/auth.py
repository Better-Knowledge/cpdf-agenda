# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Autenticação, papéis e escopos.

**A separação que este módulo existe para garantir:** um agente de
atendimento (o que conversa com o cliente final no WhatsApp/Telegram) e um
agente administrativo (o da equipe, via MCP) não têm a mesma autoridade. Até
aqui tinham — `ESCOPOS_PADRAO` era o default de toda credencial e
`exigir_escopo` nunca barrava ninguém.

Quatro formas de credencial, todas resolvendo para (org_id, escopos, ator):
- **Bearer `agk_…`** — credencial de `agent_credentials`, com escopos próprios
  e revogável. É o caminho preferido, e o que o MCP administrativo usa;
- **Bearer `ats_…`** — token de sessão de atendimento (RF-19): traz um
  `titular` assinado e restringe a credencial ao cliente daquela conversa.
  Cunhado pelo canal-service, nunca aqui;
- **Bearer JWT do Supabase** — humano/UI. Só o humano recebe `credenciais:admin`;
- **`X-Agent-Key`** — o header que a UI manda, resolvido em `agent_credentials`
  como qualquer bearer. Some quando o Supabase Auth entrar.

Sobram dois caminhos legados, ambos fechados por padrão: `X-Service-Key`, que
só responde com `atendimento_isolado` desligado (rollback), e `X-Org-Id` cru,
que só vale em `app_env=dev`. `AGENT_API_KEYS` — chave estática no ambiente —
**não existe mais**: sem linha no banco não há escopo por credencial nem
revogação sem redeploy, que são a razão de o RF-18 existir.

OAuth 2.1 (fase 2) fica no roadmap — `00` §5.4.
"""

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from uuid import UUID

import jwt
from fastapi import Request

from .config import settings
from .errors import ApiError

log = logging.getLogger("agenda.auth")

# ── Vocabulário de autoridade ────────────────────────────────────────────────

ESCOPO_READ = "agenda:read"           # catálogo, slots, grade, o PRÓPRIO compromisso
ESCOPO_WRITE = "agenda:write"         # agendar/reagendar/confirmar/fila, para um cliente
ESCOPO_CANCEL = "agenda:cancel"       # cancelar um compromisso
ESCOPO_OPERACAO = "agenda:operacao"   # a operação inteira: dia, todos os compromissos, fila
ESCOPO_ADMIN = "agenda:admin"         # escrita de serviços, recursos, janelas, bloqueios
ESCOPO_CANAL = "canal:admin"          # driver, credenciais, templates, opt-outs
ESCOPO_CREDENCIAIS = "credenciais:admin"  # emitir/revogar credenciais

ESCOPOS_CONHECIDOS = frozenset(
    {
        ESCOPO_READ, ESCOPO_WRITE, ESCOPO_CANCEL,
        ESCOPO_OPERACAO, ESCOPO_ADMIN, ESCOPO_CANAL, ESCOPO_CREDENCIAIS,
    }
)

# Papéis são PRESETS: preenchem os escopos na criação da credencial. Quem manda
# depois é a coluna `escopos` — o administrador ajusta credencial a credencial.
PAPEIS: dict[str, frozenset[str]] = {
    # O agente do canal. Não cancela: o aceite do PRD §14.4 é exatamente este.
    "atendimento": frozenset({ESCOPO_READ, ESCOPO_WRITE}),
    # Quem opera o dia a dia e enxerga a agenda inteira.
    "operacao": frozenset({ESCOPO_READ, ESCOPO_WRITE, ESCOPO_CANCEL, ESCOPO_OPERACAO}),
    # O agente administrativo do MCP: configura a plataforma.
    "administrativo": frozenset(
        {ESCOPO_READ, ESCOPO_WRITE, ESCOPO_CANCEL, ESCOPO_OPERACAO, ESCOPO_ADMIN, ESCOPO_CANAL}
    ),
}

# `credenciais:admin` NÃO entra em preset nenhum de bearer token, de propósito:
# um token administrativo comprometido não deve conseguir emitir outro token
# para sobreviver à própria revogação. Só JWT de humano recebe.
ESCOPOS_HUMANO = PAPEIS["administrativo"] | {ESCOPO_CREDENCIAIS}

# Autoridade total, usada só pelos caminhos legados enquanto durar a transição.
ESCOPOS_LEGADO = ESCOPOS_HUMANO

PREFIXO_TOKEN = "agk_"
# Espelha `sessao_atendimento.PREFIXO`. Duplicado de propósito: aquele módulo
# importa `PAPEIS` daqui, e um import no topo fecharia o ciclo.
PREFIXO_SESSAO = "ats_"


@dataclass(frozen=True)
class Credencial:
    org_id: UUID
    escopos: frozenset[str] = field(default_factory=lambda: frozenset(ESCOPOS_LEGADO))
    ator: str = "humano"  # humano | agente
    # Cliente em nome de quem o agente age. Quando presente, a credencial só
    # alcança os dados desse cliente (etapa 3).
    titular: str | None = None
    credencial_id: UUID | None = None
    nome: str = "legado"

    def pode(self, escopo: str) -> bool:
        return escopo in self.escopos


def _nao_autenticado(motivo: str) -> ApiError:
    return ApiError(
        code="NAO_AUTENTICADO",
        message=f"Credencial ausente ou inválida: {motivo}",
        hint=(
            "Envie `Authorization: Bearer agk_…` (credencial de agente), `ats_…` "
            "(sessão de atendimento) ou o JWT do Supabase. Chave estática em "
            "variável de ambiente não autentica: a credencial vive no banco."
        ),
        status_code=401,
    )


# ── Credenciais de banco ─────────────────────────────────────────────────────


def gerar_token() -> tuple[str, str, str]:
    """(token em claro, hash, prefixo). O claro só existe neste retorno."""
    token = PREFIXO_TOKEN + secrets.token_urlsafe(32)
    return token, hash_token(token), token[: len(PREFIXO_TOKEN) + 6]


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# Cache curto: sem ele, toda requisição custa uma ida extra ao banco antes da
# sessão da própria requisição. O preço é explícito — revogar leva até TTL
# segundos para valer.
_CACHE: dict[str, tuple[float, "Credencial"]] = {}
TTL_CACHE_S = 30


def limpar_cache() -> None:
    _CACHE.clear()


def _marcar_uso(db, credencial_id: UUID) -> None:
    """Registra o uso no máximo a cada 5 min: um UPDATE por requisição criaria
    contenção na mesma linha para todo o tráfego da credencial."""
    from sqlalchemy import text as sql_text

    db.execute(
        sql_text(
            "update agent_credentials set ultimo_uso_em = now() where id = :id "
            "and (ultimo_uso_em is null or ultimo_uso_em < now() - interval '5 minutes')"
        ),
        {"id": credencial_id},
    )
    db.commit()


def _resolver_credencial(token: str) -> Credencial | None:
    """Lookup cross-org por hash, em sessão PRÓPRIA e efêmera.

    É o token que revela a org, então a busca precisa acontecer antes de haver
    org — daí o modo worker. A sessão é própria de propósito: `sessao_worker`
    na sessão da requisição faria toda query seguinte daquela transação
    atravessar organizações.
    """
    from sqlalchemy import select

    from .models import AgentCredential
    from .sessao import SessionLocal, sessao_worker

    h = hash_token(token)
    agora = time.monotonic()
    if (guardado := _CACHE.get(h)) and guardado[0] > agora:
        return guardado[1]

    with SessionLocal() as db:
        sessao_worker(db)
        linha = db.scalar(
            select(AgentCredential).where(
                AgentCredential.token_hash == h,
                AgentCredential.ativo.is_(True),
                AgentCredential.revogada_em.is_(None),
            )
        )
        if linha is None:
            return None
        cred = Credencial(
            org_id=linha.org_id,
            escopos=frozenset(linha.escopos),
            ator="agente",
            credencial_id=linha.id,
            nome=linha.nome,
        )
        _marcar_uso(db, linha.id)

    _CACHE[h] = (agora + TTL_CACHE_S, cred)
    return cred


# ── Resolução da credencial da requisição ────────────────────────────────────


def _do_jwt(token: str) -> Credencial:
    cfg = settings()
    try:
        claims = jwt.decode(
            token, cfg.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated"
        )
    except jwt.PyJWTError as e:
        raise _nao_autenticado(f"JWT rejeitado ({e})") from e
    org = claims.get("org_id") or (claims.get("app_metadata") or {}).get("org_id")
    if not org:
        raise _nao_autenticado("JWT sem claim org_id")
    # Humano é quem gere credenciais — nenhum token de agente recebe isso.
    return Credencial(org_id=UUID(org), escopos=ESCOPOS_HUMANO, nome="humano")


def _da_sessao_atendimento(token: str) -> Credencial:
    """Token cunhado pelo canal: o `titular` vem assinado, não declarado.

    A partir daqui a credencial não é mais "um agente da organização X" e sim
    "um agente falando por FULANO na organização X" — e as guardas de
    propriedade (`_carregar`) têm em que se apoiar.
    """
    from .sessao_atendimento import validar

    sessao = validar(token)
    return Credencial(
        org_id=sessao.org_id,
        escopos=sessao.escopos,
        ator="agente",
        titular=sessao.titular,
        nome="atendimento",
    )


def credencial_atual(request: Request) -> Credencial:
    """Resolve a credencial e a deixa em `request.state` para a auditoria.

    O middleware de auditoria roda fora do ciclo de dependências e não tem
    como pedir esta função de novo (resolver duas vezes custaria uma ida ao
    banco por requisição). Deixar aqui é o único ponto em que a credencial
    existe com certeza.
    """
    cred = _resolver_da_requisicao(request)
    request.state.credencial = cred
    return cred


def _resolver_da_requisicao(request: Request) -> Credencial:
    cfg = settings()

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.removeprefix("Bearer ")
        if token.startswith(PREFIXO_TOKEN):
            if cred := _resolver_credencial(token):
                return cred
            raise _nao_autenticado("token desconhecido ou revogado")
        if token.startswith(PREFIXO_SESSAO):
            return _da_sessao_atendimento(token)
        return _do_jwt(token)

    # A UI manda X-Agent-Key. É o MESMO lookup do bearer: o header muda, a
    # autoridade não. Uma chave que não está em `agent_credentials` não
    # autentica — nem que esteja no ambiente.
    agent_key = request.headers.get("X-Agent-Key")
    if agent_key:
        if cred := _resolver_credencial(agent_key):
            return cred
        raise _nao_autenticado(
            "X-Agent-Key desconhecida ou revogada. Chaves de AGENT_API_KEYS não "
            "valem mais: migre com `python -m app.admin_cli importar-env`."
        )

    service_key = request.headers.get("X-Service-Key")
    if service_key:
        if not cfg.agenda_service_key or service_key != cfg.agenda_service_key:
            raise _nao_autenticado("X-Service-Key desconhecida")
        org = request.headers.get("X-Org-Id")
        if not org:
            raise _nao_autenticado("X-Service-Key sem X-Org-Id")
        if cfg.atendimento_isolado:
            # A virada do RF-19. Enquanto a flag esteve desligada, esta chave
            # valia como autoridade total sobre a organização inteira — que é
            # exatamente o que o isolamento existe para acabar. Ligada, o
            # caminho fecha: quem atende cliente usa token de sessão.
            raise _nao_autenticado(
                "X-Service-Key não vale mais na agenda (ATENDIMENTO_ISOLADO=1). "
                "Use o token de sessão que o canal cunha a cada mensagem."
            )
        log.warning("auth legada: X-Service-Key — migre para token de sessão de atendimento")
        return Credencial(org_id=UUID(org), escopos=ESCOPOS_LEGADO, ator="agente")

    if cfg.dev_mode and (org := request.headers.get("X-Org-Id")):
        return Credencial(org_id=UUID(org), escopos=ESCOPOS_LEGADO)

    raise _nao_autenticado("nenhum header de credencial presente")


def exigir_escopo(cred: Credencial, escopo: str) -> None:
    if not cred.pode(escopo):
        raise ApiError(
            code="ESCOPO_INSUFICIENTE",
            message=f"A credencial não tem o escopo '{escopo}'.",
            hint=(
                f"Esta credencial tem {sorted(cred.escopos)}. Funções administrativas "
                "exigem uma credencial de papel 'administrativo' — agentes de "
                "atendimento não as alcançam."
            ),
            status_code=403,
        )


def escopos_do_papel(papel: str) -> frozenset[str]:
    if papel not in PAPEIS:
        raise ValueError(f"papel desconhecido: {papel} (use {sorted(PAPEIS)})")
    return PAPEIS[papel]


def validar_escopos(escopos: list[str]) -> list[str]:
    if desconhecidos := set(escopos) - ESCOPOS_CONHECIDOS:
        raise ValueError(f"escopos desconhecidos: {sorted(desconhecidos)}")
    return sorted(set(escopos))
