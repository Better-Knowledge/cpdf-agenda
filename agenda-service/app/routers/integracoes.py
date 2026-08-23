# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""RF-12 — conectar e desconectar o Google Calendar.

O OAuth acontece no navegador do prestador, e é isso que molda estas rotas:

- **`POST /integracoes/google/conectar`** é autenticada e devolve a *URL* —
  não um redirect. Um `X-Agent-Key` (ou bearer) não sobrevive a um redirect
  iniciado pelo browser; devolver a URL deixa quem tem a credencial decidir
  quando navegar.
- **`GET /integracoes/google/callback`** é pública, porque quem a chama é o
  Google mandando o navegador de volta. A autoridade dela vem inteira do
  `state` assinado (ver `estado_oauth`), não de credencial nenhuma.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import crypto, estado_oauth
from .. import google_calendar as gcal
from ..auth import Credencial, credencial_atual, exigir_escopo
from ..contrato import operacao, respostas, respostas_publicas
from ..db import get_db
from ..errors import ApiError, NaoEncontrado
from ..models import GoogleCalendarLink, Resource
from ..schemas import (
    GoogleConectarIn,
    GoogleConectarOut,
    GoogleConexaoOut,
    GoogleDesconectadoOut,
)
from ..sessao import SessionLocal, sessao_org
from ..tempo import agora_utc

router = APIRouter(tags=["integrações"])

# O calendário de destino é o principal da conta conectada. Escolher outro é
# configuração que ninguém pediu ainda — e cada opção a mais na tela de OAuth
# é uma chance a mais de conectar no lugar errado.
CALENDARIO = "primary"


def _redirect_uri(request: Request) -> str:
    """Precisa ser byte a byte igual ao cadastrado no console do Google, e
    igual entre a autorização e a troca do código — o Google compara as duas."""
    from ..config import settings

    base = (settings().base_url_publica or str(request.base_url)).rstrip("/")
    return f"{base}/integracoes/google/callback"


def _exigir_app_configurado() -> None:
    if not gcal.configurado():
        raise ApiError(
            code="GOOGLE_NAO_CONFIGURADO",
            message="Este servidor não tem app OAuth do Google configurado.",
            hint=(
                "Configure GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET no .env do VPS. "
                "Sem isso, use o feed .ics (POST /ics/tokens), que não exige OAuth."
            ),
            status_code=409,
        )


@router.get(
    "/integracoes/google",
    response_model=list[GoogleConexaoOut],
    summary="Conexões Google Calendar da organização",
    responses=respostas(),
    description=(
        "Uma linha por recurso conectado. Tokens são write-only: esta rota mostra "
        "status, nunca credencial. `precisa_reconectar` fica true quando o Google "
        "passou a recusar os tokens — o push para de sair e o busy-read volta ao "
        "cálculo local."
    ),
    openapi_extra=operacao("agenda:admin"),
)
def listar_conexoes(
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> list[GoogleConexaoOut]:
    exigir_escopo(cred, "agenda:admin")
    linhas = db.execute(
        select(GoogleCalendarLink, Resource)
        .join(Resource, Resource.id == GoogleCalendarLink.resource_id)
        .where(
            GoogleCalendarLink.org_id == cred.org_id,
            GoogleCalendarLink.revogado_em.is_(None),
        )
        .order_by(GoogleCalendarLink.created_at)
    ).all()
    return [
        GoogleConexaoOut(
            resource_id=link.resource_id,
            resource_nome=recurso.nome,
            calendar_id=link.calendar_id,
            ativo=link.ativo,
            precisa_reconectar=not link.ativo,
            conectado_em=link.created_at,
        )
        for link, recurso in linhas
    ]


@router.post(
    "/integracoes/google/conectar",
    response_model=GoogleConectarOut,
    summary="Começa a conexão OAuth com o Google Calendar",
    description=(
        "Devolve a URL de consentimento do Google. Abra no navegador do prestador: "
        "ele escolhe a conta, aceita, e volta para a tela de Integrações já "
        "conectado. Escopo mínimo — criar/editar os próprios eventos e ler "
        "livre/ocupado. O link vale 10 minutos."
    ),
    responses=respostas("NAO_ENCONTRADO", "GOOGLE_NAO_CONFIGURADO"),
    openapi_extra=operacao("agenda:admin"),
)
def conectar(
    dados: GoogleConectarIn,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> GoogleConectarOut:
    exigir_escopo(cred, "agenda:admin")
    _exigir_app_configurado()
    recurso = db.scalar(
        select(Resource).where(Resource.id == dados.resource_id, Resource.org_id == cred.org_id)
    )
    if recurso is None:
        raise NaoEncontrado("Recurso", str(dados.resource_id))
    url = gcal.url_de_autorizacao(
        state=estado_oauth.emitir(cred.org_id, recurso.id),
        redirect_uri=_redirect_uri(request),
    )
    return GoogleConectarOut(url=url)


@router.get(
    "/integracoes/google/callback",
    summary="Retorno do consentimento do Google (público)",
    responses=respostas_publicas("OAUTH_ESTADO_INVALIDO"),
    description=(
        "Chamada pelo navegador do prestador, redirecionado pelo Google. Não exige "
        "credencial: a autoridade vem do `state` assinado, que diz de qual "
        "organização e recurso é a conexão. Termina redirecionando para a tela de "
        "Integrações."
    ),
    include_in_schema=True,
    openapi_extra={"security": []},  # público de propósito
)
def callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str = Query(),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    from ..config import settings

    base = (settings().base_url_publica or str(request.base_url)).rstrip("/")
    org_id, resource_id = estado_oauth.validar(state)
    if error or not code:
        # O prestador clicou "cancelar" na tela do Google. Não é falha do
        # sistema: volta para a tela dizendo isso.
        return RedirectResponse(f"{base}/app/integracoes?google=cancelado", status_code=303)

    dados = gcal.trocar_codigo(code, _redirect_uri(request))
    creds = gcal.Credenciais.de_resposta(dados)
    if not creds.refresh_token:
        # Sem refresh_token a conexão morre em uma hora. Acontece quando a
        # conta já havia consentido antes sem `prompt=consent`; melhor recusar
        # agora do que quebrar silenciosamente na primeira renovação.
        return RedirectResponse(f"{base}/app/integracoes?google=sem_refresh", status_code=303)

    with SessionLocal() as db:
        sessao_org(db, org_id)
        link = db.scalar(
            select(GoogleCalendarLink).where(
                GoogleCalendarLink.org_id == org_id,
                GoogleCalendarLink.resource_id == resource_id,
            )
        )
        if link is None:
            link = GoogleCalendarLink(
                org_id=org_id, resource_id=resource_id, calendar_id=CALENDARIO, credenciais={}
            )
            db.add(link)
        link.credenciais = crypto.cifrar(creds.como_dict())
        link.calendar_id = CALENDARIO
        link.ativo = True
        link.revogado_em = None
        db.commit()
    return RedirectResponse(f"{base}/app/integracoes?google=conectado", status_code=303)


@router.delete(
    "/integracoes/google/{resource_id}",
    response_model=GoogleDesconectadoOut,
    summary="Desconecta o Google Calendar de um recurso",
    description=(
        "Revoga os tokens no Google e apaga as credenciais daqui (RF-12). Os eventos "
        "já criados no calendário **permanecem lá** — apagá-los seria destruir a "
        "agenda de alguém a partir de uma desconexão. Idempotente."
    ),
    responses=respostas("NAO_ENCONTRADO"),
    openapi_extra=operacao("agenda:admin"),
)
def desconectar(
    resource_id: UUID,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> GoogleDesconectadoOut:
    exigir_escopo(cred, "agenda:admin")
    link = db.scalar(
        select(GoogleCalendarLink).where(
            GoogleCalendarLink.org_id == cred.org_id,
            GoogleCalendarLink.resource_id == resource_id,
            GoogleCalendarLink.revogado_em.is_(None),
        )
    )
    if link is None:
        return GoogleDesconectadoOut(
            resource_id=resource_id,
            desconectado=False,
            aviso="Este recurso já não tinha conexão com o Google.",
        )
    try:
        creds = gcal.Credenciais.de_dict(crypto.decifrar(link.credenciais))
        gcal.revogar(creds.refresh_token)
    except Exception:  # noqa: BLE001 — segredo ilegível não impede desconectar
        pass
    link.ativo = False
    link.revogado_em = agora_utc()
    link.credenciais = {}  # o segredo sai do banco na desconexão
    db.commit()
    return GoogleDesconectadoOut(
        resource_id=resource_id,
        desconectado=True,
        aviso=(
            "Tokens revogados e apagados. Os eventos já criados continuam no "
            "calendário do prestador — a agenda não apaga o que não criou agora."
        ),
    )
