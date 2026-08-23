"""`00` §5.8 — toda ação de agente é rastreável.

**Por que aqui e não no conector MCP.** Seria mais fácil auditar dentro do
`agenda-admin-mcp`: ele já sabe o nome da tool e os argumentos. Mas então as
ações do **agente de atendimento** — o WhatsApp, a superfície que mais
importa vigiar — nunca apareceriam no log, porque elas não passam por MCP
nenhum. Auditoria no serviço de domínio cobre todo caminho de entrada: MCP,
UI, canal e curl.

**O que entra no log.** Toda escrita (POST/PATCH/PUT/DELETE) e toda recusa
por autoridade (403). Leitura bem-sucedida fica de fora de propósito: um
agente consultando `/slots` a cada mensagem geraria mais linhas de auditoria
do que de negócio, e o sinal desapareceria no volume.

**O que NÃO entra:** o corpo da requisição, nem hasheado. Ler o corpo aqui
exigiria interceptar o stream ASGI e devolvê-lo intacto ao handler — risco
real de quebrar requisição legítima por causa de log. O `args_hash` cobre
rota, query string e `Idempotency-Key`, que é o identificador que o próprio
chamador deu à intenção: suficiente para correlacionar tentativas, e sem
nenhuma chance de guardar dado de cliente.

**401 não é auditável aqui:** sem credencial resolvida não há organização a
que atribuir a linha, e `org_id` é `not null`. Token desconhecido ou revogado
fica no log da aplicação (`agenda.auth`), onde já é registrado.
"""

import hashlib
import logging
import time
from typing import Any

from .models import AgentAuditLog

log = logging.getLogger("agenda.auditoria")

METODOS_DE_MUDANCA = frozenset({"POST", "PATCH", "PUT", "DELETE"})
HEADER_SERVIDOR = b"x-mcp-server"
HEADER_TOOL = b"x-mcp-tool"


def _cabecalho(scope: dict, nome: bytes) -> str | None:
    for chave, valor in scope.get("headers", []):
        if chave == nome:
            return valor.decode("latin-1")
    return None


def _hash_argumentos(scope: dict) -> str:
    """Rota + query + Idempotency-Key. Nunca o valor de nada."""
    bruto = "|".join(
        [
            scope.get("path", ""),
            scope.get("query_string", b"").decode("latin-1"),
            _cabecalho(scope, b"idempotency-key") or "",
        ]
    )
    return hashlib.sha256(bruto.encode()).hexdigest()[:32]


def registrar(
    cred,
    *,
    mcp_server: str,
    tool_name: str,
    args_hash: str,
    resultado: str,
    error_code: str | None,
    latencia_ms: int | None,
) -> None:
    """Grava a linha em sessão própria. Falha aqui NUNCA derruba a requisição
    — que a esta altura já foi respondida —, mas grita no log: uma auditoria
    que some em silêncio é pior do que não ter auditoria, porque dá a
    impressão de cobertura."""
    from .sessao import SessionLocal, sessao_org

    try:
        with SessionLocal() as db:
            sessao_org(db, cred.org_id)
            db.add(
                AgentAuditLog(
                    org_id=cred.org_id,
                    mcp_server=mcp_server,
                    tool_name=tool_name,
                    client_id=cred.credencial_id,
                    actor=cred.nome,
                    titular=cred.titular,
                    args_hash=args_hash,
                    resultado=resultado,
                    error_code=error_code,
                    latencia_ms=latencia_ms,
                )
            )
            db.commit()
    except Exception:
        log.exception(
            "AUDITORIA PERDIDA: %s %s por %s (org %s)",
            resultado, tool_name, cred.nome, cred.org_id,
        )


class Auditoria:
    """Middleware ASGI puro — não `BaseHTTPMiddleware`.

    Dois motivos concretos: o `scope["state"]` (onde `request.state` vive) é
    lido daqui sem recriar o Request, e a gravação acontece DEPOIS de a
    resposta ter saído pelo `send`, então o log não entra no tempo que o
    cliente espera.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        observado: dict[str, int] = {}

        async def send_observado(mensagem):
            if mensagem["type"] == "http.response.start":
                observado["code"] = mensagem["status"]
                # Cronometra até a resposta SAIR, não até o ciclo acabar: tasks
                # de fundo (a oferta da fila, que fala com o canal) rodam depois
                # disso e inflariam a latência com tempo que o cliente não esperou.
                observado["ms"] = int((time.perf_counter() - inicio) * 1000)
            await send(mensagem)

        inicio = time.perf_counter()
        scope.setdefault("state", {})
        await self.app(scope, receive, send_observado)

        cred = scope["state"].get("credencial")
        if cred is None:
            return  # rota sem credencial (/health) ou 401 antes de haver org

        codigo = observado.get("code", 0)
        recusado = codigo in (401, 403)
        if scope["method"] not in METODOS_DE_MUDANCA and not recusado:
            return

        registrar(
            cred,
            mcp_server=_cabecalho(scope, HEADER_SERVIDOR) or "http",
            tool_name=_cabecalho(scope, HEADER_TOOL) or f"{scope['method']} {scope['path']}",
            args_hash=_hash_argumentos(scope),
            resultado="recusado" if recusado else ("ok" if codigo < 400 else "erro"),
            error_code=scope["state"].get("error_code"),
            latencia_ms=observado.get("ms"),
        )
