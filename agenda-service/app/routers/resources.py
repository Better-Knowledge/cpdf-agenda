from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import idempotency as idem
from ..auth import Credencial, credencial_atual, exigir_escopo
from ..db import get_db
from ..models import Resource
from ..schemas import Pagina, ResourceIn, ResourceOut

router = APIRouter(tags=["catálogo"])


@router.get(
    "/resources",
    response_model=Pagina[ResourceOut],
    summary="Lista profissionais, salas e equipamentos ativos",
)
def listar_resources(
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> Pagina[ResourceOut]:
    exigir_escopo(cred, "agenda:read")
    linhas = db.scalars(
        select(Resource).where(Resource.org_id == cred.org_id, Resource.ativo).order_by(Resource.nome)
    ).all()
    return Pagina(items=[ResourceOut.model_validate(r) for r in linhas])


@router.post(
    "/resources",
    response_model=ResourceOut,
    status_code=201,
    summary="Cadastra um recurso (profissional, sala, equipamento)",
)
def criar_resource(
    dados: ResourceIn,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:write")
    if repetida := idem.buscar(db, cred.org_id, request):
        return repetida
    recurso = Resource(org_id=cred.org_id, **dados.model_dump())
    db.add(recurso)
    db.flush()
    corpo = ResourceOut.model_validate(recurso)
    idem.gravar(db, cred.org_id, request, corpo.model_dump(mode="json"), 201)
    db.commit()
    return corpo
