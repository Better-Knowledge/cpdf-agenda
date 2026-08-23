"""Quem sou eu — e, adiante, gestão de credenciais.

`GET /credenciais/eu` é deliberadamente aberto a qualquer credencial
autenticada: descobrir a própria autoridade não é privilégio, e é o que
permite a um agente (ou ao conector MCP) falhar rápido e com mensagem legível
em vez de tentar uma ação que levaria 403.

Emitir credencial NÃO tem rota: o bootstrap é por CLI (`app/admin_cli.py`).
"""

from fastapi import APIRouter, Depends

from ..auth import PAPEIS, Credencial, credencial_atual
from ..contrato import respostas
from ..schemas import QuemSouOut

router = APIRouter(tags=["credenciais"])


@router.get(
    "/credenciais/eu",
    response_model=QuemSouOut,
    summary="A autoridade desta credencial",
    description=(
        "Devolve organização, papel, escopos e — quando for uma credencial de "
        "atendimento — o cliente em nome de quem ela age. Consulte antes de assumir "
        "que uma operação é permitida: funções administrativas exigem papel "
        "`administrativo`, e agentes de atendimento não as alcançam."
    ),
    responses=respostas(),
    openapi_extra={"x-escopo-requerido": "nenhum (qualquer credencial autenticada)"},
)
def quem_sou(cred: Credencial = Depends(credencial_atual)) -> QuemSouOut:
    papel = next((p for p, e in PAPEIS.items() if e == cred.escopos), None)
    return QuemSouOut(
        org_id=cred.org_id,
        nome=cred.nome,
        papel=papel,
        ator=cred.ator,
        escopos=sorted(cred.escopos),
        titular=cred.titular,
    )
