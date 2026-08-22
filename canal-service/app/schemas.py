from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class EnviarIn(BaseModel):
    """Contrato do adapter (`00` §4.8): sessão × template é a assimetria
    que prepara a migração para a API oficial da Meta."""

    destinatario: str = Field(min_length=8, description="Telefone E.164, ex.: +5511...")
    tipo: Literal["sessao", "template"]
    template_nome: str | None = None
    template_id: UUID | None = None
    variaveis: dict[str, str] = {}
    texto: str | None = Field(default=None, description="Permitido apenas quando tipo=sessao")


class EnviarOut(BaseModel):
    message_id: int
    status: str
    corpo_renderizado: str


class TemplateIn(BaseModel):
    nome: str = Field(min_length=1)
    corpo: str = Field(min_length=1)
    aprovado_meta: bool = False


class TemplateOut(BaseModel):
    id: UUID
    nome: str
    corpo: str
    versao: int
    aprovado_meta: bool
    ativo: bool


class ConfigIn(BaseModel):
    driver: Literal["evolution", "zapi", "meta"]
    numero: str = Field(min_length=8)
    instancia: str = Field(min_length=1, description="Identificador da instância no driver")
    credenciais: dict[str, str]
    confirmo_numero_dedicado: bool = Field(
        default=False,
        description="O produto recusa número pessoal — declare que o número é dedicado.",
    )


class MensagemOut(BaseModel):
    id: int
    direcao: str
    telefone: str
    tipo: str | None
    corpo_renderizado: str | None
    driver: str
    status: str
    erro: str | None
    created_at: str
