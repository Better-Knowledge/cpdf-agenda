from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import Credencial, credencial_atual, exigir_escopo
from ..booking import carregar_servico, recursos_do_servico, slots_do_recurso
from ..db import get_db
from ..errors import NaoEncontrado
from ..schemas import SlotOut
from ..tempo import exigir_aware

router = APIRouter(tags=["slots"])


@router.get(
    "/slots",
    response_model=list[SlotOut],
    summary="Horários realmente livres para um serviço",
    description=(
        "Motor de disponibilidade (RF-02): desconta duração, buffers, bloqueios e "
        "agendamentos existentes. Chame SEMPRE antes de tentar agendar e sempre que o "
        "cliente mencionar um dia ou período ('quinta de tarde'). Converta a expressão "
        "em um intervalo ISO 8601 com offset (America/Sao_Paulo) antes de chamar. "
        "Retorno vazio: amplie o intervalo e ofereça as 3 alternativas mais próximas — "
        "nunca responda apenas 'indisponível'. Não use para ver compromissos já "
        "marcados (use GET /agenda/day)."
    ),
)
def consultar_slots(
    service_id: UUID,
    from_: datetime = Query(alias="from", description="Início do intervalo, ISO 8601 com offset"),
    to: datetime = Query(description="Fim do intervalo, ISO 8601 com offset"),
    resource_id: UUID | None = Query(default=None, description="Opcional: recurso específico"),
    limit: int = Query(default=20, le=50),
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> list[SlotOut]:
    exigir_escopo(cred, "agenda:read")
    exigir_aware(from_, "from")
    exigir_aware(to, "to")
    servico = carregar_servico(db, cred.org_id, service_id)
    recursos = recursos_do_servico(db, servico)
    if resource_id is not None:
        recursos = [r for r in recursos if r.id == resource_id]
        if not recursos:
            raise NaoEncontrado("Recurso", str(resource_id))
    slots: list[SlotOut] = []
    for recurso in recursos:
        for inicio in slots_do_recurso(db, servico, recurso.id, from_, to, limite=limit):
            slots.append(SlotOut.de_inicio(inicio, servico.duracao_min, recurso.id))
    slots.sort(key=lambda s: s.inicio)
    return slots[:limit]
