from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import idempotency as idem
from ..auth import Credencial, credencial_atual, exigir_escopo
from ..contrato import operacao, respostas
from ..db import get_db
from ..errors import NaoEncontrado
from ..models import Resource
from ..schemas import Pagina, ResourceIn, ResourceOut, ResourcePatch

router = APIRouter(tags=["catálogo"])


@router.get(
    "/resources",
    response_model=Pagina[ResourceOut],
    summary="Lista profissionais, salas e equipamentos ativos",
    responses=respostas(),
    openapi_extra=operacao("agenda:read"),
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
    description="O recurso é o que não pode ser agendado duas vezes no mesmo horário. Aceita Idempotency-Key.",
    responses=respostas(),
    openapi_extra=operacao("agenda:admin", idempotente=True),
)
def criar_resource(
    dados: ResourceIn,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:admin")
    if repetida := idem.buscar(db, cred.org_id, request, cred.titular):
        return repetida
    recurso = Resource(org_id=cred.org_id, **dados.model_dump())
    db.add(recurso)
    db.flush()
    corpo = ResourceOut.model_validate(recurso)
    idem.gravar(db, cred.org_id, request, corpo.model_dump(mode="json"), 201, cred.titular)
    db.commit()
    return corpo


def _carregar(db: Session, cred: Credencial, resource_id: UUID) -> Resource:
    recurso = db.scalar(
        select(Resource).where(Resource.id == resource_id, Resource.org_id == cred.org_id)
    )
    if recurso is None:
        raise NaoEncontrado("Recurso", str(resource_id))
    return recurso


@router.patch(
    "/resources/{resource_id}",
    response_model=ResourceOut,
    summary="Altera um recurso (parcial)",
    description=(
        "Só os campos enviados mudam. Renomear não afeta agendamentos: eles apontam "
        "para o id. Reative um recurso desativado com `{ativo: true}`."
    ),
    responses=respostas("NAO_ENCONTRADO"),
    openapi_extra=operacao("agenda:admin"),
)
def alterar_resource(
    resource_id: UUID,
    dados: ResourcePatch,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:admin")
    recurso = _carregar(db, cred, resource_id)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(recurso, campo, valor)
    db.commit()
    return ResourceOut.model_validate(recurso)


@router.delete(
    "/resources/{resource_id}",
    response_model=ResourceOut,
    summary="Desativa um recurso (soft delete)",
    description=(
        "Como em serviços: o recurso sai do catálogo e da oferta de slots, mas os "
        "agendamentos e o histórico dele continuam existindo — apagar de verdade "
        "deixaria compromissos apontando para o vazio. A grade semanal e os "
        "bloqueios permanecem, e voltam a valer se o recurso for reativado com "
        "PATCH `{ativo: true}`. Idempotente."
    ),
    responses=respostas("NAO_ENCONTRADO"),
    openapi_extra=operacao("agenda:admin"),
)
def desativar_resource(
    resource_id: UUID,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:admin")
    recurso = _carregar(db, cred, resource_id)
    recurso.ativo = False
    db.commit()
    return ResourceOut.model_validate(recurso)
