from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.orm import Session

from .. import idempotency as idem
from ..auth import Credencial, credencial_atual, exigir_escopo
from ..db import get_db
from ..errors import ApiError, NaoEncontrado
from ..models import AvailabilityBlock, AvailabilityRule, Resource
from ..schemas import BlockIn, BlockOut, RuleIn, RuleOut, RulePatch
from ..tempo import utc

router = APIRouter(tags=["grade"])


def _exigir_recurso(db: Session, cred: Credencial, resource_id) -> None:
    if not db.scalar(
        select(Resource).where(Resource.id == resource_id, Resource.org_id == cred.org_id)
    ):
        raise NaoEncontrado("Recurso", str(resource_id))


@router.post(
    "/availability/rules",
    response_model=RuleOut,
    status_code=201,
    summary="Adiciona janela de trabalho semanal a um recurso",
    description="dia_semana: 0=segunda … 6=domingo. Horas em hora local America/Sao_Paulo (RF-02).",
)
def criar_rule(
    dados: RuleIn,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:write")
    _exigir_recurso(db, cred, dados.resource_id)
    if repetida := idem.buscar(db, cred.org_id, request):
        return repetida
    regra = AvailabilityRule(org_id=cred.org_id, **dados.model_dump())
    db.add(regra)
    db.flush()
    corpo = RuleOut.model_validate(regra)
    idem.gravar(db, cred.org_id, request, corpo.model_dump(mode="json"), 201)
    db.commit()
    return corpo


@router.get("/availability/rules", response_model=list[RuleOut], summary="Grade semanal da organização")
def listar_rules(
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> list[RuleOut]:
    exigir_escopo(cred, "agenda:read")
    linhas = db.scalars(
        select(AvailabilityRule)
        .where(AvailabilityRule.org_id == cred.org_id)
        .order_by(AvailabilityRule.dia_semana, AvailabilityRule.hora_inicio)
    ).all()
    return [RuleOut.model_validate(r) for r in linhas]


@router.patch(
    "/availability/rules/{rule_id}",
    response_model=RuleOut,
    summary="Altera uma janela da grade semanal",
    description="Só os campos enviados mudam. A alteração vale para os slots futuros na hora.",
)
def alterar_rule(
    rule_id: UUID,
    dados: RulePatch,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:write")
    regra = db.scalar(
        select(AvailabilityRule).where(
            AvailabilityRule.id == rule_id, AvailabilityRule.org_id == cred.org_id
        )
    )
    if regra is None:
        raise NaoEncontrado("Janela da grade", str(rule_id))
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(regra, campo, valor)
    if regra.hora_fim <= regra.hora_inicio:
        raise ApiError(
            code="PERIODO_INVALIDO",
            message="O fim da janela precisa ser depois do início.",
            hint="Confira hora_inicio e hora_fim após a alteração.",
        )
    db.commit()
    return RuleOut.model_validate(regra)


@router.delete(
    "/availability/rules/{rule_id}",
    summary="Remove uma janela da grade semanal",
    description=(
        "Exclusão real: grade é configuração, não histórico. O motor de slots deixa "
        "de oferecer os horários desta janela imediatamente; agendamentos já feitos "
        "não mudam. Idempotente: remover de novo devolve o mesmo resultado."
    ),
)
def remover_rule(
    rule_id: UUID,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> dict:
    exigir_escopo(cred, "agenda:write")
    removidas = db.execute(
        delete(AvailabilityRule).where(
            AvailabilityRule.id == rule_id, AvailabilityRule.org_id == cred.org_id
        )
    ).rowcount
    db.commit()
    return {"id": str(rule_id), "removida": bool(removidas)}


@router.delete(
    "/availability/blocks/{block_id}",
    summary="Remove um bloqueio pontual",
    description=(
        "Exclusão real: os horários do período voltam a ser ofertados na hora. "
        "Idempotente."
    ),
)
def remover_block(
    block_id: UUID,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> dict:
    exigir_escopo(cred, "agenda:write")
    removidos = db.execute(
        delete(AvailabilityBlock).where(
            AvailabilityBlock.id == block_id, AvailabilityBlock.org_id == cred.org_id
        )
    ).rowcount
    db.commit()
    return {"id": str(block_id), "removido": bool(removidos)}


@router.get(
    "/availability/blocks",
    response_model=list[BlockOut],
    summary="Bloqueios pontuais vigentes ou futuros",
    description="Lista bloqueios cujo fim ainda não passou. Filtre por recurso se quiser.",
)
def listar_blocks(
    resource_id: UUID | None = None,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> list[BlockOut]:
    exigir_escopo(cred, "agenda:read")
    q = select(AvailabilityBlock).where(
        AvailabilityBlock.org_id == cred.org_id,
        text("upper(periodo) >= now()"),
    )
    if resource_id:
        q = q.where(AvailabilityBlock.resource_id == resource_id)
    return [
        BlockOut(
            id=b.id,
            resource_id=b.resource_id,
            inicio=b.periodo.lower,
            fim=b.periodo.upper,
            motivo=b.motivo,
        )
        for b in db.scalars(q.order_by(text("lower(periodo)")))
    ]


@router.post(
    "/availability/blocks",
    response_model=BlockOut,
    status_code=201,
    summary="Bloqueia um período pontual (feriado, almoço, férias)",
    description="Início e fim em ISO 8601 com offset. O motivo aparece na agenda do dia.",
)
def criar_block(
    dados: BlockIn,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:write")
    _exigir_recurso(db, cred, dados.resource_id)
    if dados.fim <= dados.inicio:
        raise ApiError(
            code="PERIODO_INVALIDO",
            message="O fim do bloqueio precisa ser depois do início.",
            hint="Inverta os valores ou confira o offset de fuso.",
        )
    if repetida := idem.buscar(db, cred.org_id, request):
        return repetida
    bloco = AvailabilityBlock(
        org_id=cred.org_id,
        resource_id=dados.resource_id,
        periodo=Range(utc(dados.inicio), utc(dados.fim)),
        motivo=dados.motivo,
    )
    db.add(bloco)
    db.flush()
    corpo = BlockOut(
        id=bloco.id,
        resource_id=bloco.resource_id,
        inicio=dados.inicio,
        fim=dados.fim,
        motivo=bloco.motivo,
    )
    idem.gravar(db, cred.org_id, request, corpo.model_dump(mode="json"), 201)
    db.commit()
    return corpo
