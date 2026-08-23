# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>


from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import delete, select, tuple_
from sqlalchemy.orm import Session

from .. import idempotency as idem
from ..auth import Credencial, credencial_atual, exigir_escopo
from ..contrato import operacao, respostas
from ..db import get_db
from ..errors import NaoEncontrado
from ..models import Resource, Service, ServiceResource
from ..pagination import codificar_cursor, decodificar_cursor
from ..schemas import Pagina, ServiceIn, ServiceOut, ServicePatch

router = APIRouter(tags=["catálogo"])


@router.get(
    "/services",
    response_model=Pagina[ServiceOut],
    summary="Lista os serviços da organização",
    description=(
        "Use antes de consultar slots ou agendar: o service_id daqui é obrigatório "
        "nas demais chamadas. Paginação por limit/cursor."
    ),
    responses=respostas("CURSOR_INVALIDO"),
    openapi_extra=operacao("agenda:read"),
)
def listar_services(
    request: Request,
    ativo: bool | None = Query(default=True),
    limit: int = Query(default=20, le=50),
    cursor: str | None = None,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> Pagina[ServiceOut]:
    exigir_escopo(cred, "agenda:read")
    q = select(Service).where(Service.org_id == cred.org_id)
    if ativo is not None:
        q = q.where(Service.ativo == ativo)
    if cursor:
        c = decodificar_cursor(cursor)
        q = q.where(tuple_(Service.created_at, Service.id) > (c["created_at"], c["id"]))
    linhas = db.scalars(q.order_by(Service.created_at, Service.id).limit(limit + 1)).all()
    proxima = (
        codificar_cursor(linhas[limit - 1].created_at, linhas[limit - 1].id)
        if len(linhas) > limit
        else None
    )
    return Pagina(items=[ServiceOut.model_validate(s) for s in linhas[:limit]], next_cursor=proxima)


@router.post(
    "/services",
    response_model=ServiceOut,
    status_code=201,
    summary="Cadastra um serviço",
    description=(
        "Nome, duração em minutos, preço (string decimal, BRL) e buffers. "
        "Alterar a duração depois não muda agendamentos já existentes (RF-01). "
        "Aceita Idempotency-Key."
    ),
    responses=respostas("NAO_ENCONTRADO"),
    openapi_extra=operacao("agenda:admin", idempotente=True),
)
def criar_service(
    dados: ServiceIn,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:admin")
    if repetida := idem.buscar(db, cred.org_id, request, cred.titular):
        return repetida
    servico = Service(org_id=cred.org_id, **dados.model_dump(exclude={"resource_ids"}))
    db.add(servico)
    db.flush()
    for rid in dados.resource_ids:
        if not db.scalar(select(Resource).where(Resource.id == rid, Resource.org_id == cred.org_id)):
            raise NaoEncontrado("Recurso", str(rid))
        db.add(ServiceResource(service_id=servico.id, resource_id=rid))
    corpo = ServiceOut.model_validate(servico)
    idem.gravar(db, cred.org_id, request, corpo.model_dump(mode="json"), 201, cred.titular)
    db.commit()
    return corpo


def _carregar(db: Session, cred: Credencial, service_id: UUID) -> Service:
    servico = db.scalar(
        select(Service).where(Service.id == service_id, Service.org_id == cred.org_id)
    )
    if servico is None:
        raise NaoEncontrado("Serviço", str(service_id))
    return servico


@router.patch(
    "/services/{service_id}",
    response_model=ServiceOut,
    summary="Altera um serviço (parcial)",
    description=(
        "Só os campos enviados mudam. Alterar a duração NÃO altera agendamentos já "
        "existentes (RF-01) — só afeta slots e agendamentos futuros. resource_ids, "
        "quando enviado, substitui os vínculos atuais."
    ),
    responses=respostas("NAO_ENCONTRADO"),
    openapi_extra=operacao("agenda:admin"),
)
def alterar_service(
    service_id: UUID,
    dados: ServicePatch,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:admin")
    servico = _carregar(db, cred, service_id)
    mudancas = dados.model_dump(exclude_unset=True, exclude={"resource_ids"})
    for campo, valor in mudancas.items():
        setattr(servico, campo, valor)
    if dados.resource_ids is not None:
        db.execute(delete(ServiceResource).where(ServiceResource.service_id == servico.id))
        for rid in dados.resource_ids:
            if not db.scalar(
                select(Resource).where(Resource.id == rid, Resource.org_id == cred.org_id)
            ):
                raise NaoEncontrado("Recurso", str(rid))
            db.add(ServiceResource(service_id=servico.id, resource_id=rid))
    db.commit()
    return ServiceOut.model_validate(servico)


@router.delete(
    "/services/{service_id}",
    response_model=ServiceOut,
    summary="Desativa um serviço (soft delete)",
    description=(
        "Entidade de negócio não é apagada: o serviço sai do catálogo e da oferta de "
        "slots, mas agendamentos e histórico existentes ficam intactos. Reative com "
        "PATCH {ativo: true}. Idempotente."
    ),
    responses=respostas("NAO_ENCONTRADO"),
    openapi_extra=operacao("agenda:admin"),
)
def desativar_service(
    service_id: UUID,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:admin")
    servico = _carregar(db, cred, service_id)
    servico.ativo = False
    db.commit()
    return ServiceOut.model_validate(servico)
