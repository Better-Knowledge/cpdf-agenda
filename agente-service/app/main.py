"""agente-service — o orquestrador do inbound (PRD §8, IA-04).

O segundo padrão de IA do programa: aqui a IA mora NO AGENTE, não dentro do
serviço de domínio. A agenda oferece contratos amigáveis a agente (slots com
alternativas, erros com `hint`, datas com `label_humano`) e quem pensa é este
serviço — via API hoje, via MCP na etapa 9.

Ele não tem banco: o estado vive na agenda e no canal.
"""

import logging
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import fluxo
from .config import settings

logging.basicConfig(level=settings().log_level)
log = logging.getLogger("agente")

app = FastAPI(
    title="Agente da Agenda — agente-service",
    version="0.1.0",
    description=(
        "Recebe o inbound normalizado do canal, classifica a intenção (IA-04) e age "
        "pela API da agenda. Cancelamento nunca é automático — vai para o humano."
    ),
)


class InboundIn(BaseModel):
    org_id: UUID
    telefone: str = Field(min_length=8)
    texto: str
    message_id: str | None = None
    timestamp: str | None = None


def _autenticado(request: Request) -> bool:
    cfg = settings()
    chave = request.headers.get("X-Service-Key", "")
    return bool(cfg.agente_service_key) and chave == cfg.agente_service_key


@app.get("/health", summary="Liveness do agente")
def health() -> dict:
    cfg = settings()
    return {
        "status": "ok",
        # sem chave de LLM o agente funciona só com regras — e diz isso
        "classificacao": "regras+llm" if cfg.anthropic_api_key else "somente_regras",
    }


@app.post(
    "/inbound",
    summary="Mensagem do cliente, normalizada pelo canal",
    description=(
        "Chamado pelo canal-service depois de registrar a mensagem. Opt-out já foi "
        "tratado por regra antes de chegar aqui — o agente nunca decide sobre isso."
    ),
)
def inbound(dados: InboundIn, request: Request):
    if not _autenticado(request):
        return JSONResponse(
            status_code=401,
            content={
                "code": "NAO_AUTENTICADO",
                "message": "Chamada sem credencial service-to-service válida.",
                "hint": "Envie X-Service-Key com a credencial do agente.",
                "retryable": False,
            },
        )
    try:
        resultado = fluxo.tratar(dados.org_id, dados.telefone, dados.texto)
    except Exception:
        # Nunca devolve 5xx ao canal: a mensagem já está registrada lá e o
        # humano vê a conversa de qualquer forma.
        log.exception("falha ao tratar inbound de %s", dados.telefone)
        return {"acao": "erro_interno_logado"}
    return {
        "intencao": resultado.intencao,
        "confianca": resultado.confianca,
        "acao": resultado.acao,
        "resposta": resultado.resposta,
        **resultado.detalhes,
    }
