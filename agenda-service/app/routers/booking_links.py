"""RF-13 — link público de auto-agendamento.

A conversa continua sendo a tese do módulo; o link existe para o cliente que
prefere clicar. Duas metades neste arquivo:

**Gestão** (`/booking-links`, `agenda:admin`) — criar, ativar, desativar.

**Página pública** (`/publico/agendar/{slug}`) — sem credencial, e é aí que
mora o cuidado. Ela usa o **mesmo** `GET /slots` e o **mesmo** caminho de
criação de compromisso: sem rota privilegiada, sem regra paralela, a mesma
constraint anti-double-booking. O que ela ganha de específico é limite por
IP e uma superfície de leitura mínima — a página nunca lista compromissos,
nem diz quem é o recurso, nem confirma a existência de um cliente.
"""

import re
import unicodedata
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import booking, enderecos, rate_limit
from ..auth import Credencial, credencial_atual, exigir_escopo
from ..contrato import operacao, respostas, respostas_publicas
from ..db import get_db
from ..errors import ApiError, NaoEncontrado
from ..models import BookingLink, Service
from ..schemas import (
    AgendamentoPublicoIn,
    AgendamentoPublicoOut,
    BookingLinkIn,
    BookingLinkOut,
    BookingLinkPatch,
    PaginaPublicaOut,
    SlotOut,
)
from ..sessao import SessionLocal, sessao_org, sessao_worker
from ..tempo import agora_utc, exigir_aware, label_humano

router = APIRouter(tags=["link público"])

# Limites da página pública. Generosos para quem está escolhendo horário,
# apertados para quem está agendando: criar compromisso mexe na agenda de
# alguém, consultar não.
LIMITE_LEITURA = (60, 60)  # 60 por minuto
LIMITE_ESCRITA = (5, 3600)  # 5 por hora

JANELA_MAXIMA = timedelta(days=60)


def _slugificar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")[:60] or "agendar"


def _url(request: Request, slug: str) -> str:
    from ..config import settings

    base = (settings().base_url_publica or str(request.base_url)).rstrip("/")
    return f"{base}/app/agendar/{slug}"


def _saida(request: Request, link: BookingLink) -> BookingLinkOut:
    return BookingLinkOut(
        id=link.id,
        service_id=link.service_id,
        resource_id=link.resource_id,
        slug=link.slug,
        url=_url(request, link.slug),
        ativo=link.ativo,
        exige_caucao=link.exige_caucao,
        valor_caucao=link.valor_caucao,
        created_at=link.created_at,
    )


# ── Gestão (autenticada) ─────────────────────────────────────────────────────


@router.get(
    "/booking-links",
    response_model=list[BookingLinkOut],
    summary="Lista os links públicos de auto-agendamento",
    responses=respostas(),
    openapi_extra=operacao("agenda:admin"),
)
def listar(
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> list[BookingLinkOut]:
    exigir_escopo(cred, "agenda:admin")
    linhas = db.scalars(
        select(BookingLink).where(BookingLink.org_id == cred.org_id).order_by(BookingLink.created_at)
    ).all()
    return [_saida(request, linha) for linha in linhas]


@router.post(
    "/booking-links",
    response_model=BookingLinkOut,
    status_code=201,
    summary="Cria um link público de auto-agendamento",
    description=(
        "O link consome o mesmo motor de slots e o mesmo caminho de agendamento da "
        "API — nenhuma regra paralela. A caução, se configurada, apenas **informa** o "
        "valor na página nesta fase; a cobrança via Pix é roadmap."
    ),
    responses=respostas("NAO_ENCONTRADO", "SLUG_INDISPONIVEL"),
    openapi_extra=operacao("agenda:admin"),
)
def criar(
    dados: BookingLinkIn,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> BookingLinkOut:
    exigir_escopo(cred, "agenda:admin")
    servico = booking.carregar_servico(db, cred.org_id, dados.service_id)
    link = _inserir_com_slug_livre(
        db,
        BookingLink(
            org_id=cred.org_id,
            service_id=servico.id,
            resource_id=dados.resource_id,
            exige_caucao=dados.exige_caucao,
            valor_caucao=dados.valor_caucao,
        ),
        _slugificar(dados.slug or servico.nome),
    )
    db.commit()
    db.refresh(link)
    return _saida(request, link)


def _inserir_com_slug_livre(db: Session, link: BookingLink, desejado: str) -> BookingLink:
    """O slug é único **globalmente** (é uma URL), mas a RLS só deixa esta
    sessão enxergar a própria organização.

    Consultar antes de inserir, portanto, não detecta colisão com outra org —
    e nem deveria: saber que `corte` já existe é saber algo sobre a agenda de
    um estranho. Deixamos a constraint falar e reagimos ao conflito com um
    sufixo aleatório, que é o único jeito de resolver sem vazar a existência
    da linha alheia.
    """
    import secrets

    for tentativa in range(4):
        link.slug = desejado if tentativa == 0 else f"{desejado}-{secrets.token_hex(3)}"
        try:
            with db.begin_nested():
                db.add(link)
                db.flush()
            return link
        except IntegrityError as e:
            if "booking_links_slug_key" not in str(e.orig):
                raise
    raise ApiError(
        code="SLUG_INDISPONIVEL",
        message="Não foi possível reservar um endereço para este link.",
        hint="Envie um `slug` diferente no corpo da chamada.",
        status_code=409,
    )


def _carregar(db: Session, cred: Credencial, link_id: UUID) -> BookingLink:
    link = db.scalar(
        select(BookingLink).where(BookingLink.id == link_id, BookingLink.org_id == cred.org_id)
    )
    if link is None:
        raise NaoEncontrado("Link de agendamento", str(link_id))
    return link


@router.patch(
    "/booking-links/{link_id}",
    response_model=BookingLinkOut,
    summary="Altera um link (ativar, desativar, caução)",
    description="Desativado, a URL responde com mensagem clara em vez de sumir.",
    responses=respostas("NAO_ENCONTRADO"),
    openapi_extra=operacao("agenda:admin"),
)
def alterar(
    link_id: UUID,
    dados: BookingLinkPatch,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> BookingLinkOut:
    exigir_escopo(cred, "agenda:admin")
    link = _carregar(db, cred, link_id)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(link, campo, valor)
    db.commit()
    db.refresh(link)
    return _saida(request, link)


@router.delete(
    "/booking-links/{link_id}",
    response_model=BookingLinkOut,
    summary="Desativa um link público",
    description="Soft delete: a URL passa a explicar que está desativada. Idempotente.",
    responses=respostas("NAO_ENCONTRADO"),
    openapi_extra=operacao("agenda:admin"),
)
def desativar(
    link_id: UUID,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> BookingLinkOut:
    exigir_escopo(cred, "agenda:admin")
    link = _carregar(db, cred, link_id)
    link.ativo = False
    db.commit()
    db.refresh(link)
    return _saida(request, link)


# ── Página pública (sem credencial) ──────────────────────────────────────────


def _resolver_slug(slug: str) -> tuple[BookingLink, Service]:
    """Slug → link + serviço, em sessão worker efêmera.

    O slug é público e não revela org nenhuma; é ele que diz de quem é a
    página. Mesmo padrão do feed .ics e do lookup de credencial: worker só
    para descobrir a org, nunca na sessão que serve o resto da requisição.
    """
    with SessionLocal() as db:
        sessao_worker(db)
        linha = db.execute(
            select(BookingLink, Service)
            .join(Service, Service.id == BookingLink.service_id)
            .where(BookingLink.slug == slug)
        ).first()
    if linha is None:
        raise NaoEncontrado("Link de agendamento", slug)
    link, servico = linha
    if not link.ativo or not servico.ativo:
        raise ApiError(
            code="LINK_INATIVO",
            message="Este link de agendamento está desativado no momento.",
            hint="Fale com o prestador pelo WhatsApp — a conversa continua funcionando.",
            status_code=409,
        )
    return link, servico


@router.get(
    "/publico/agendar/{slug}",
    response_model=PaginaPublicaOut,
    summary="Dados da página pública de agendamento",
    description=(
        "Sem credencial. Devolve o mínimo para a página: serviço, duração e preço — "
        "nunca a agenda, nunca o recurso, nunca outro cliente. Limite por IP."
    ),
    responses=respostas_publicas("NAO_ENCONTRADO", "LINK_INATIVO", "MUITAS_REQUISICOES"),
    openapi_extra={"security": []},
)
def pagina(slug: str, request: Request) -> PaginaPublicaOut:
    rate_limit.exigir("publico-leitura", rate_limit.ip_do(request), limite=LIMITE_LEITURA[0], janela_segundos=LIMITE_LEITURA[1])
    link, servico = _resolver_slug(slug)
    aviso = None
    if link.exige_caucao and link.valor_caucao:
        aviso = (
            f"Este agendamento pede um sinal de R$ {link.valor_caucao:.2f}. "
            "O prestador combina o pagamento com você."
        )
    return PaginaPublicaOut(
        slug=link.slug,
        servico=servico.nome,
        duracao_min=servico.duracao_min,
        preco=f"{servico.preco:.2f}",
        exige_caucao=link.exige_caucao,
        valor_caucao=None if link.valor_caucao is None else f"{link.valor_caucao:.2f}",
        aviso_caucao=aviso,
    )


@router.get(
    "/publico/agendar/{slug}/slots",
    response_model=list[SlotOut],
    summary="Horários livres do link público",
    description=(
        "O mesmo motor de `GET /slots` (RF-02), inclusive o busy-read do Google "
        "(RF-12). Só horários **livres** saem daqui: a página nunca revela o que "
        "está ocupado nem por quem."
    ),
    responses=respostas_publicas(
        "NAO_ENCONTRADO", "LINK_INATIVO", "MUITAS_REQUISICOES", "DATA_SEM_FUSO"
    ),
    openapi_extra={"security": []},
)
def slots_publicos(
    slug: str,
    request: Request,
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    limit: int = Query(default=20, le=50),
) -> list[SlotOut]:
    rate_limit.exigir("publico-leitura", rate_limit.ip_do(request), limite=LIMITE_LEITURA[0], janela_segundos=LIMITE_LEITURA[1])
    exigir_aware(from_, "from")
    exigir_aware(to, "to")
    link, servico = _resolver_slug(slug)
    if to - from_ > JANELA_MAXIMA:
        to = from_ + JANELA_MAXIMA
    saida: list[SlotOut] = []
    with SessionLocal() as db:
        sessao_org(db, link.org_id)
        servico = db.get(Service, link.service_id)
        recursos = booking.recursos_do_servico(db, servico)
        if link.resource_id is not None:
            recursos = [r for r in recursos if r.id == link.resource_id]
        for recurso in recursos:
            for inicio in booking.slots_do_recurso(db, servico, recurso.id, from_, to, limite=limit):
                saida.append(SlotOut.de_inicio(inicio, servico.duracao_min, recurso.id))
    saida.sort(key=lambda s: s.inicio)
    return saida[:limit]


@router.post(
    "/publico/agendar/{slug}",
    response_model=AgendamentoPublicoOut,
    status_code=201,
    summary="Agenda pelo link público",
    description=(
        "Mesma constraint anti-double-booking e mesma régua de confirmação e "
        "lembretes (RF-05) do agendamento por conversa — o compromisso entra com "
        "`origem: cliente`. Coleta mínima: nome e telefone. Horário ocupado devolve "
        "409 com as 3 alternativas mais próximas no payload. Limite estreito por IP."
    ),
    responses=respostas_publicas(
        "NAO_ENCONTRADO", "LINK_INATIVO", "MUITAS_REQUISICOES", "SLOT_INDISPONIVEL",
        "DATA_SEM_FUSO", "DATA_NO_PASSADO",
    ),
    openapi_extra={"security": []},
)
def agendar_publico(
    slug: str, dados: AgendamentoPublicoIn, request: Request
) -> AgendamentoPublicoOut:
    ip = rate_limit.ip_do(request)
    rate_limit.exigir("publico-escrita", ip, limite=LIMITE_ESCRITA[0], janela_segundos=LIMITE_ESCRITA[1])
    link, _ = _resolver_slug(slug)
    if dados.inicio < agora_utc():
        raise ApiError(
            code="DATA_NO_PASSADO",
            message="O horário escolhido já passou.",
            hint="Recarregue a página e escolha um horário na lista de livres.",
        )
    with SessionLocal() as db:
        sessao_org(db, link.org_id)
        servico = booking.carregar_servico(db, link.org_id, link.service_id)
        recursos = booking.recursos_do_servico(db, servico)
        if link.resource_id is not None:
            recursos = [r for r in recursos if r.id == link.resource_id]
        if not recursos:
            raise NaoEncontrado("Recurso do link", slug)
        # Sem recurso escolhido pelo cliente: o primeiro que tiver o horário
        # livre leva. Quem clica num link quer um horário, não uma sala.
        erro: ApiError | None = None
        for recurso in recursos:
            try:
                ap = booking.criar_appointment(
                    db,
                    org_id=link.org_id,
                    servico=servico,
                    resource_id=recurso.id,
                    inicio=dados.inicio,
                    cliente_nome=dados.cliente_nome.strip(),
                    cliente_telefone=enderecos.normalizar(dados.cliente_telefone),
                    origem="cliente",
                )
                db.commit()
                break
            except ApiError as e:
                erro = e
        else:
            raise erro
        return AgendamentoPublicoOut(
            id=ap.id,
            servico=servico.nome,
            inicio=ap.periodo.lower,
            label_humano=label_humano(ap.periodo.lower),
            mensagem=(
                f"Agendado: {servico.nome}, {label_humano(ap.periodo.lower)}. "
                "Você receberá a confirmação pelo WhatsApp."
            ),
        )
