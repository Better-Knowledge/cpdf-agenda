"""T-09 — canal de WhatsApp na UI, por procuração.

O canal-service nunca é exposto ao navegador (PRD §11): a UI fala com o
agenda-service, que repassa a chamada com a credencial service-to-service.
Os erros do canal já seguem o contrato {code, message, hint, retryable} e
sobem intactos — este router não os traduz, só os transporta.
"""

from typing import Any

from fastapi import APIRouter, Depends

from .. import canal_client
from ..auth import Credencial, credencial_atual, exigir_escopo
from ..contrato import operacao, respostas
from ..errors import ApiError
from ..schemas import (
    CanalConexaoOut,
    CanalConfigCriadaOut,
    CanalConfigIn,
    CanalConfigOut,
    CanalOptoutOut,
    CanalTemplateIn,
    CanalTemplateOut,
    RemocaoOptoutOut,
)

router = APIRouter(tags=["canal"])


def _proxy(metodo: str, rota: str, cred: Credencial, corpo: Any | None = None) -> Any:
    try:
        status, dados = canal_client.chamar(metodo, rota, org_id=cred.org_id, corpo=corpo)
    except canal_client.CanalIndisponivel as e:
        raise ApiError(
            code="CANAL_INDISPONIVEL",
            message="O canal de WhatsApp não respondeu.",
            hint="Tente de novo em instantes — a operação é segura para repetir.",
            retryable=True,
            status_code=502,
        ) from e
    if status >= 400:
        raise ApiError(
            code=dados.get("code", "ERRO_DO_CANAL"),
            message=dados.get("message", "O canal respondeu com erro."),
            hint=dados.get("hint", ""),
            retryable=dados.get("retryable", False),
            status_code=status,
            extra={
                k: v
                for k, v in dados.items()
                if k not in ("code", "message", "hint", "retryable")
            },
        )
    return dados


@router.get(
    "/canal/config",
    response_model=CanalConfigOut,
    summary="Configuração vigente do canal (sem credenciais)",
    description="Credenciais de driver são write-only e nunca voltam. `configurado=false` não é erro.",
    responses=respostas("CANAL_INDISPONIVEL"),
    openapi_extra=operacao("agenda:read"),
)
def ler_config(cred: Credencial = Depends(credencial_atual)):
    exigir_escopo(cred, "agenda:read")
    return _proxy("GET", "/canal/config", cred)


@router.post(
    "/canal/config",
    response_model=CanalConfigCriadaOut,
    status_code=201,
    summary="Configura o driver do canal (write-only)",
    description=(
        "Trocar de driver é só trocar esta configuração — nenhum módulo muda. "
        "As credenciais são cifradas no canal e NUNCA voltam. O produto recusa número "
        "que não seja dedicado. Reconfigurar rotaciona o segredo do webhook."
    ),
    responses=respostas("NUMERO_PESSOAL_RECUSADO", "CANAL_INDISPONIVEL"),
    openapi_extra=operacao("agenda:write"),
)
def configurar(dados: CanalConfigIn, cred: Credencial = Depends(credencial_atual)):
    exigir_escopo(cred, "agenda:write")
    return _proxy("POST", "/canal/config", cred, dados.model_dump())


@router.post(
    "/canal/conectar",
    response_model=CanalConexaoOut,
    summary="Conecta o canal (QR no WhatsApp, ativação do bot no Telegram)",
    description=(
        "Registra o webhook do inbound e deixa o canal pronto para conversar. No "
        "Evolution devolve o QR (data URI) para parear em WhatsApp > Aparelhos "
        "conectados; no Telegram já volta `conectado` — bot não pareia. Z-API e Meta "
        "conectam no painel do fornecedor."
    ),
    responses=respostas("CANAL_NAO_CONFIGURADO", "FALHA_NO_DRIVER", "CANAL_INDISPONIVEL"),
    openapi_extra=operacao("agenda:write"),
)
def conectar(cred: Credencial = Depends(credencial_atual)):
    exigir_escopo(cred, "agenda:write")
    return _proxy("POST", "/canal/conectar", cred)


@router.get(
    "/canal/status",
    response_model=CanalConexaoOut,
    summary="Estado da conexão instância ↔ WhatsApp",
    responses=respostas("CANAL_NAO_CONFIGURADO", "FALHA_NO_DRIVER", "CANAL_INDISPONIVEL"),
    openapi_extra=operacao("agenda:read"),
)
def status_conexao(cred: Credencial = Depends(credencial_atual)):
    exigir_escopo(cred, "agenda:read")
    return _proxy("GET", "/canal/status", cred)


@router.get(
    "/canal/templates",
    response_model=list[CanalTemplateOut],
    summary="Templates de mensagem ativa da organização",
    responses=respostas("CANAL_INDISPONIVEL"),
    openapi_extra=operacao("agenda:read"),
)
def listar_templates(cred: Credencial = Depends(credencial_atual)):
    exigir_escopo(cred, "agenda:read")
    return _proxy("GET", "/canal/templates", cred)


@router.post(
    "/canal/templates",
    response_model=CanalTemplateOut,
    status_code=201,
    summary="Cadastra (ou versiona) um template de mensagem ativa",
    description=(
        "Mesmo nome → nova versão. O texto é redigido uma vez, revisado por humano e "
        "versionado (IA-02) — a IA não improvisa mensagem ativa por cliente."
    ),
    responses=respostas("CANAL_INDISPONIVEL"),
    openapi_extra=operacao("agenda:write"),
)
def criar_template(dados: CanalTemplateIn, cred: Credencial = Depends(credencial_atual)):
    exigir_escopo(cred, "agenda:write")
    return _proxy("POST", "/canal/templates", cred, dados.model_dump())


@router.get(
    "/canal/optouts",
    response_model=list[CanalOptoutOut],
    summary="Clientes que pediram para não receber mensagem ativa",
    responses=respostas("CANAL_INDISPONIVEL"),
    openapi_extra=operacao("agenda:read"),
)
def listar_optouts(cred: Credencial = Depends(credencial_atual)):
    exigir_escopo(cred, "agenda:read")
    return _proxy("GET", "/canal/optouts", cred)


@router.delete(
    "/canal/optouts/{telefone}",
    response_model=RemocaoOptoutOut,
    summary="Remove um opt-out (reativa mensagens ativas para o telefone)",
    description="Só com pedido explícito do cliente ao humano. Idempotente.",
    responses=respostas("CANAL_INDISPONIVEL"),
    openapi_extra=operacao("agenda:write"),
)
def remover_optout(telefone: str, cred: Credencial = Depends(credencial_atual)):
    exigir_escopo(cred, "agenda:write")
    return _proxy("DELETE", f"/canal/optouts/{telefone}", cred)
