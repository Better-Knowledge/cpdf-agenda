# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""RF-11 — feed .ics somente-leitura, a opção de calendário sem OAuth.

O segredo é o token na URL: quem o tem lê a agenda daquele recurso, sem
autenticar. Daí as três decisões desta rota — token de 32 bytes aleatórios,
revogável a qualquer momento, e modo `privado` para quando a URL for parar
num calendário compartilhado.

A rota pública é a única do serviço que responde sem credencial. Ela resolve
o token em sessão worker própria e efêmera (é o token que revela a org, como
na autenticação) e só então abre uma sessão presa àquela org para ler os
compromissos — a RLS continua valendo para a leitura dos dados.
"""

import secrets
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.orm import Session

from .. import ics
from ..auth import Credencial, credencial_atual, exigir_escopo
from ..contrato import operacao, respostas, respostas_publicas
from ..db import get_db
from ..errors import NaoEncontrado
from ..models import Appointment, IcsToken, Resource, Service
from ..schemas import IcsTokenCriadoOut, IcsTokenIn, IcsTokenOut
from ..sessao import SessionLocal, sessao_org, sessao_worker
from ..tempo import agora_utc

router = APIRouter(tags=["calendário"])

# Janela do feed: um mês para trás dá contexto ao prestador; três meses para
# frente cobre o horizonte de agendamento sem inchar o arquivo.
PASSADO = timedelta(days=30)
FUTURO = timedelta(days=90)


def _base(request: Request) -> str:
    from ..config import settings

    return (settings().base_url_publica or str(request.base_url)).rstrip("/")


def _url(request: Request, token: str) -> str:
    return f"{_base(request)}/ics/{token}.ics"


def _url_redigida(request: Request, token: str) -> str:
    return f"{_base(request)}/ics/{token[:6]}***.ics"


def _saida(request: Request, linha: IcsToken) -> IcsTokenOut:
    return IcsTokenOut(
        id=linha.id,
        resource_id=linha.resource_id,
        modo=linha.modo,
        url=_url_redigida(request, linha.token),
        revogado_em=linha.revogado_em,
        created_at=linha.created_at,
    )


@router.get(
    "/ics/tokens",
    response_model=list[IcsTokenOut],
    summary="Lista os feeds de calendário da organização",
    responses=respostas(),
    description=(
        "As URLs saem redigidas: o token nelas dá acesso de leitura à agenda sem "
        "autenticação. Para reassinar o feed, use POST /ics/tokens/{id}/revelar."
    ),
    openapi_extra=operacao("agenda:admin"),
)
def listar_tokens(
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> list[IcsTokenOut]:
    exigir_escopo(cred, "agenda:admin")
    linhas = db.scalars(
        select(IcsToken).where(IcsToken.org_id == cred.org_id).order_by(IcsToken.created_at)
    ).all()
    return [_saida(request, linha) for linha in linhas]


@router.post(
    "/ics/tokens",
    response_model=IcsTokenCriadoOut,
    status_code=201,
    summary="Cria um feed de calendário (.ics)",
    description=(
        "Devolve a URL completa para assinar no Google/Apple Calendar. O feed é "
        "**visão consolidada, não notificação**: o Google relê calendários assinados "
        "em ciclos de horas. Tempo real no Google é papel do push (RF-12); lembrete "
        "em tempo real é papel do canal (RF-05)."
    ),
    responses=respostas("NAO_ENCONTRADO"),
    openapi_extra=operacao("agenda:admin"),
)
def criar_token(
    dados: IcsTokenIn,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> IcsTokenCriadoOut:
    exigir_escopo(cred, "agenda:admin")
    if dados.resource_id is not None:
        existe = db.scalar(
            select(Resource).where(
                Resource.id == dados.resource_id, Resource.org_id == cred.org_id
            )
        )
        if existe is None:
            raise NaoEncontrado("Recurso", str(dados.resource_id))
    linha = IcsToken(
        org_id=cred.org_id,
        resource_id=dados.resource_id,
        token=secrets.token_urlsafe(32),
        modo=dados.modo,
    )
    db.add(linha)
    db.commit()
    db.refresh(linha)
    base = _saida(request, linha)
    return IcsTokenCriadoOut(**base.model_dump(), url_completa=_url(request, linha.token))


@router.post(
    "/ics/tokens/{token_id}/revelar",
    response_model=IcsTokenCriadoOut,
    summary="Revela a URL completa de um feed",
    description=(
        "Para reassinar o calendário em outro dispositivo. Vazou o link? Não revele: "
        "revogue e crie outro — a URL antiga para de responder na hora."
    ),
    responses=respostas("NAO_ENCONTRADO"),
    openapi_extra=operacao("agenda:admin"),
)
def revelar_token(
    token_id: UUID,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> IcsTokenCriadoOut:
    exigir_escopo(cred, "agenda:admin")
    linha = db.scalar(
        select(IcsToken).where(IcsToken.id == token_id, IcsToken.org_id == cred.org_id)
    )
    if linha is None:
        raise NaoEncontrado("Feed de calendário", str(token_id))
    base = _saida(request, linha)
    return IcsTokenCriadoOut(**base.model_dump(), url_completa=_url(request, linha.token))


@router.post(
    "/ics/tokens/{token_id}/revogar",
    response_model=IcsTokenOut,
    summary="Revoga um feed de calendário",
    description=(
        "A URL passa a responder 404 imediatamente. Idempotente. O calendário já "
        "assinado no Google não some sozinho — o prestador remove a assinatura lá."
    ),
    responses=respostas("NAO_ENCONTRADO"),
    openapi_extra=operacao("agenda:admin"),
)
def revogar_token(
    token_id: UUID,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> IcsTokenOut:
    exigir_escopo(cred, "agenda:admin")
    linha = db.scalar(
        select(IcsToken).where(IcsToken.id == token_id, IcsToken.org_id == cred.org_id)
    )
    if linha is None:
        raise NaoEncontrado("Feed de calendário", str(token_id))
    if linha.revogado_em is None:
        linha.revogado_em = agora_utc()
        db.commit()
        db.refresh(linha)
    return _saida(request, linha)


def _resolver(token: str) -> IcsToken | None:
    """Token → linha, em sessão worker própria (é o token que revela a org).

    Mesmo padrão de `auth._resolver_credencial`: nunca ligue o modo worker na
    sessão da requisição — o GUC vale para a transação inteira e dali em
    diante toda query cruzaria organizações.
    """
    with SessionLocal() as db:
        sessao_worker(db)
        return db.scalar(
            select(IcsToken).where(IcsToken.token == token, IcsToken.revogado_em.is_(None))
        )


def montar_feed(linha: IcsToken) -> str:
    agora = agora_utc()
    with SessionLocal() as db:
        sessao_org(db, linha.org_id)
        q = (
            select(Appointment, Service, Resource)
            .join(Service, Service.id == Appointment.service_id)
            .join(Resource, Resource.id == Appointment.resource_id)
            .where(
                Appointment.org_id == linha.org_id,
                # Cancelado sai do feed na próxima leitura (critério do RF-11).
                Appointment.status.in_(("agendado", "confirmado", "realizado")),
                Appointment.periodo.overlaps(Range(agora - PASSADO, agora + FUTURO)),
            )
            .order_by(Appointment.periodo)
        )
        if linha.resource_id is not None:
            q = q.where(Appointment.resource_id == linha.resource_id)
        eventos = []
        nomes = set()
        for ap, servico, recurso in db.execute(q):
            nomes.add(recurso.nome)
            titulo, descricao = ics.titulo_e_descricao(
                modo=linha.modo,
                servico=servico.nome,
                cliente=ap.cliente_nome,
                status=ap.status,
                inicio=ap.periodo.lower,
            )
            eventos.append(
                ics.Evento(
                    uid=f"{ap.id}@agenda.better-knowledge.com",
                    inicio=ap.periodo.lower,
                    fim=ap.periodo.upper,
                    titulo=titulo,
                    descricao=descricao,
                    atualizado_em=ap.updated_at,
                )
            )
    nome = "Agenda Inteligente"
    if linha.resource_id is not None and nomes:
        nome = f"Agenda — {sorted(nomes)[0]}"
    return ics.gerar(nome, eventos, agora)


@router.get(
    "/ics/{token}.ics",
    summary="Feed de calendário assinável (público, token na URL)",
    description=(
        "Não exige credencial: o segredo é o token. Assine no Google Calendar "
        "(«Outros calendários» → «Do URL») ou no Apple Calendar. Token revogado "
        "responde 404. **Não é canal de notificação** — o Google relê em ciclos de "
        "horas."
    ),
    response_class=Response,
    responses={
        200: {
            "content": {"text/calendar": {}},
            "description": "Calendário iCalendar (RFC 5545)",
        },
        **respostas_publicas("NAO_ENCONTRADO"),
    },
    include_in_schema=True,
    openapi_extra={"security": []},  # público de propósito
)
def feed(token: str) -> Response:
    linha = _resolver(token)
    if linha is None:
        # 404 e não 403: distinguir "revogado" de "nunca existiu" contaria ao
        # curioso que ele acertou um token de verdade.
        raise NaoEncontrado("Feed de calendário", token[:6] + "***")
    return Response(
        content=montar_feed(linha),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="agenda.ics"',
            "Cache-Control": "public, max-age=300",
        },
    )
