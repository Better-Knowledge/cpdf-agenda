"""Quem sou eu — e, adiante, gestão de credenciais.

`GET /credenciais/eu` é deliberadamente aberto a qualquer credencial
autenticada: descobrir a própria autoridade não é privilégio, e é o que
permite a um agente (ou ao conector MCP) falhar rápido e com mensagem legível
em vez de tentar uma ação que levaria 403.

**O bootstrap continua sendo CLI** (`app/admin_cli.py`): a primeira
credencial administrativa de uma organização nasce no VPS, por quem tem
acesso ao servidor. O que estas rotas acrescentam é a gestão do dia a dia —
emitir, listar e revogar — para quem já tem `credenciais:admin`.

A linha que nenhuma rota atravessa: **`credenciais:admin` não é delegável
aqui**. Uma credencial capaz de emitir outra sobrevive à própria revogação,
que é exatamente o que a revogação existe para impedir. Quem precisa desse
escopo recebe pela CLI, por decisão de quem administra o servidor.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import idempotency as idem
from ..auth import (
    ESCOPO_CREDENCIAIS,
    PAPEIS,
    Credencial,
    credencial_atual,
    escopos_do_papel,
    exigir_escopo,
    gerar_token,
    limpar_cache,
)
from ..contrato import operacao, respostas
from ..db import get_db
from ..errors import ApiError, NaoEncontrado
from ..models import AgentCredential
from ..schemas import (
    CredencialCriadaOut,
    CredencialIn,
    CredencialOut,
    QuemSouOut,
    RevogacaoOut,
)
from ..tempo import agora_utc

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


AVISO_CACHE = (
    "A revogação vale imediatamente para novas resoluções, mas cada processo "
    "guarda a credencial por até 30 segundos — o token pode ser aceito nesse "
    "intervalo. É o preço, explícito, de não ir ao banco a cada requisição."
)


@router.get(
    "/credenciais",
    response_model=list[CredencialOut],
    summary="Credenciais de agente da organização",
    description=(
        "Quem tem acesso à agenda por integração, com que autoridade e quando usou "
        "pela última vez. O token **nunca** volta aqui: o banco guarda só o SHA-256, "
        "e o `prefixo` existe para você identificar a linha."
    ),
    responses=respostas(),
    openapi_extra=operacao("credenciais:admin"),
)
def listar(
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> list[CredencialOut]:
    exigir_escopo(cred, ESCOPO_CREDENCIAIS)
    linhas = db.scalars(
        select(AgentCredential)
        .where(AgentCredential.org_id == cred.org_id)
        .order_by(AgentCredential.criada_em)
    ).all()
    return [CredencialOut.model_validate(c) for c in linhas]


@router.post(
    "/credenciais",
    response_model=CredencialCriadaOut,
    status_code=201,
    summary="Emite uma credencial de agente",
    description=(
        "O token em claro aparece **uma única vez**, nesta resposta — guarde-o na "
        "hora. O papel é só o preset dos escopos; ajuste-os no corpo se precisar. "
        "`credenciais:admin` não pode ser concedido por aqui: uma credencial capaz "
        "de emitir outra sobreviveria à própria revogação. Aceita Idempotency-Key."
    ),
    responses=respostas("ESCOPO_NAO_DELEGAVEL"),
    openapi_extra=operacao("credenciais:admin", idempotente=True),
)
def emitir(
    dados: CredencialIn,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, ESCOPO_CREDENCIAIS)
    if repetida := idem.buscar(db, cred.org_id, request, cred.titular):
        return repetida
    if dados.papel not in PAPEIS:
        raise ApiError(
            code="PAYLOAD_INVALIDO",
            message=f"Papel desconhecido: {dados.papel}.",
            hint=f"Use um destes: {', '.join(sorted(PAPEIS))}.",
            status_code=422,
        )
    escopos = sorted(set(dados.escopos)) if dados.escopos else sorted(escopos_do_papel(dados.papel))
    _recusar_delegacao(escopos)
    if desconhecidos := set(escopos) - set().union(*PAPEIS.values()) - {ESCOPO_CREDENCIAIS}:
        raise ApiError(
            code="PAYLOAD_INVALIDO",
            message=f"Escopos desconhecidos: {sorted(desconhecidos)}.",
            hint="Consulte GET /credenciais/eu para ver os escopos que existem.",
            status_code=422,
        )

    token, token_hash, prefixo = gerar_token()
    linha = AgentCredential(
        org_id=cred.org_id,
        nome=dados.nome,
        papel=dados.papel,
        escopos=escopos,
        token_hash=token_hash,
        prefixo=prefixo,
    )
    db.add(linha)
    db.flush()
    corpo = CredencialCriadaOut(**CredencialOut.model_validate(linha).model_dump(), token=token)
    # A resposta gravada na idempotência CONTÉM o token em claro. É o preço de
    # a emissão ser repetível: sem isso, um retry de rede criaria uma segunda
    # credencial órfã, que é pior — ninguém sabe que ela existe para revogar.
    idem.gravar(db, cred.org_id, request, corpo.model_dump(mode="json"), 201, cred.titular)
    db.commit()
    return corpo


def _recusar_delegacao(escopos: list[str]) -> None:
    if ESCOPO_CREDENCIAIS in escopos:
        raise ApiError(
            code="ESCOPO_NAO_DELEGAVEL",
            message="`credenciais:admin` não pode ser concedido por esta rota.",
            hint=(
                "Uma credencial que emite credenciais sobrevive à própria revogação. "
                "Se realmente for necessário, emita pelo servidor: "
                "`make credencial` / `python -m app.admin_cli emitir … --escopos …`."
            ),
            status_code=403,
        )


@router.delete(
    "/credenciais/{credencial_id}",
    response_model=RevogacaoOut,
    summary="Revoga uma credencial de agente",
    description=(
        "A credencial para de autenticar. Não é exclusão: a linha fica, com "
        "`revogada_em` preenchido, porque o log de auditoria aponta para ela e um "
        "log que referencia um id inexistente não responde 'quem fez isso'. "
        "Idempotente."
    ),
    responses=respostas("NAO_ENCONTRADO"),
    openapi_extra=operacao("credenciais:admin"),
)
def revogar(
    credencial_id: UUID,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> RevogacaoOut:
    exigir_escopo(cred, ESCOPO_CREDENCIAIS)
    linha = db.scalar(
        select(AgentCredential).where(
            AgentCredential.id == credencial_id, AgentCredential.org_id == cred.org_id
        )
    )
    if linha is None:
        raise NaoEncontrado("Credencial", str(credencial_id))
    ja_estava = linha.revogada_em is not None
    if not ja_estava:
        linha.ativo = False
        linha.revogada_em = agora_utc()
        db.commit()
    limpar_cache()  # vale já neste processo; os outros esperam o TTL
    return RevogacaoOut(id=linha.id, revogada=not ja_estava, aviso=AVISO_CACHE)
