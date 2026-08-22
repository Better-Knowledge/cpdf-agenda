
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from .. import idempotency as idem
from ..auth import Credencial, credencial_atual, exigir_escopo
from ..db import get_db
from ..errors import NaoEncontrado
from ..models import Resource, Service, ServiceResource
from ..pagination import codificar_cursor, decodificar_cursor
from ..schemas import Pagina, ServiceIn, ServiceOut

router = APIRouter(tags=["catálogo"])


@router.get(
    "/services",
    response_model=Pagina[ServiceOut],
    summary="Lista os serviços da organização",
    description=(
        "Use antes de consultar slots ou agendar: o service_id daqui é obrigatório "
        "nas demais chamadas. Paginação por limit/cursor."
    ),
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
)
def criar_service(
    dados: ServiceIn,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:write")
    if repetida := idem.buscar(db, cred.org_id, request):
        return repetida
    servico = Service(org_id=cred.org_id, **dados.model_dump(exclude={"resource_ids"}))
    db.add(servico)
    db.flush()
    for rid in dados.resource_ids:
        if not db.scalar(select(Resource).where(Resource.id == rid, Resource.org_id == cred.org_id)):
            raise NaoEncontrado("Recurso", str(rid))
        db.add(ServiceResource(service_id=servico.id, resource_id=rid))
    corpo = ServiceOut.model_validate(servico)
    idem.gravar(db, cred.org_id, request, corpo.model_dump(mode="json"), 201)
    db.commit()
    return corpo
