from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import confirmacao
from .. import idempotency as idem
from ..auth import Credencial, credencial_atual, exigir_escopo
from ..booking import (
    _evento,
    _historico,
    carregar_servico,
    criar_appointment,
    reagendar,
    recursos_do_servico,
)
from ..contrato import operacao, respostas
from ..db import get_db
from ..errors import ApiError, NaoEncontrado
from ..models import Appointment, AppointmentHistory
from ..schemas import (
    AgendaDiaOut,
    AppointmentIn,
    AppointmentOut,
    CancelIn,
    HistoricoOut,
    RescheduleIn,
)
from ..tempo import TZ, label_humano

router = APIRouter(tags=["agendamentos"])


def _out(ap: Appointment) -> AppointmentOut:
    return AppointmentOut(
        id=ap.id,
        service_id=ap.service_id,
        resource_id=ap.resource_id,
        cliente_nome=ap.cliente_nome,
        cliente_telefone=ap.cliente_telefone,
        inicio=ap.periodo.lower,
        fim=ap.periodo.upper,
        label_humano=label_humano(ap.periodo.lower),
        status=ap.status,
        origem=ap.origem,
        risco_no_show=ap.risco_no_show,
        observacoes=ap.observacoes,
        series_id=ap.series_id,
    )


def _carregar(db: Session, cred: Credencial, appointment_id: UUID) -> Appointment:
    ap = db.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id, Appointment.org_id == cred.org_id
        )
    )
    if ap is None:
        raise NaoEncontrado("Compromisso", str(appointment_id))
    return ap


@router.post(
    "/appointments",
    response_model=AppointmentOut,
    status_code=201,
    summary="Agenda um horário",
    description=(
        "Exige serviço + horário + cliente identificado (nome e telefone) — RF-03. "
        "Sem resource_id, usa o primeiro recurso do serviço com o slot livre. "
        "Horário ocupado responde 409 SLOT_INDISPONIVEL com as 3 alternativas mais "
        "próximas já no payload. Aceita Idempotency-Key (obrigatório para agentes)."
    ),
    responses=respostas("NAO_ENCONTRADO", "SLOT_INDISPONIVEL", "DATA_SEM_FUSO"),
    openapi_extra=operacao("agenda:write", idempotente=True),
)
def agendar(
    dados: AppointmentIn,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:write")
    if repetida := idem.buscar(db, cred.org_id, request):
        return repetida
    servico = carregar_servico(db, cred.org_id, dados.service_id)
    recursos = recursos_do_servico(db, servico)
    if dados.resource_id is not None:
        recursos = [r for r in recursos if r.id == dados.resource_id]
    if not recursos:
        raise NaoEncontrado("Recurso", str(dados.resource_id))
    ap = None
    ultimo_erro: ApiError | None = None
    for recurso in recursos:
        try:
            ap = criar_appointment(
                db,
                cred.org_id,
                servico,
                recurso.id,
                dados.inicio,
                dados.cliente_nome,
                dados.cliente_telefone,
                dados.origem,
                dados.observacoes,
            )
            break
        except ApiError as e:
            if e.code != "SLOT_INDISPONIVEL":
                raise
            ultimo_erro = e
    if ap is None:
        raise ultimo_erro or ApiError(
            code="SLOT_INDISPONIVEL",
            message="Nenhum recurso do serviço está livre neste horário.",
            hint="Consulte GET /slots e ofereça as alternativas ao cliente.",
            status_code=409,
        )
    corpo = _out(ap)
    idem.gravar(db, cred.org_id, request, corpo.model_dump(mode="json"), 201)
    db.commit()
    return corpo


@router.post(
    "/appointments/{appointment_id}/reschedule",
    response_model=AppointmentOut,
    summary="Reagenda de forma atômica",
    description=(
        "Ou o novo horário é reservado e o antigo liberado na mesma transação, ou nada "
        "muda (RF-06). Conflito responde 409 com alternativas. O compromisso volta ao "
        "status 'agendado' — a confirmação anterior não vale para o novo horário."
    ),
    responses=respostas(
        "NAO_ENCONTRADO", "SLOT_INDISPONIVEL", "STATUS_INCOMPATIVEL", "DATA_SEM_FUSO"
    ),
    openapi_extra=operacao("agenda:write", idempotente=True),
)
def reagendar_endpoint(
    appointment_id: UUID,
    dados: RescheduleIn,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:write")
    if repetida := idem.buscar(db, cred.org_id, request):
        return repetida
    ap = _carregar(db, cred, appointment_id)
    if ap.status in ("cancelado", "realizado", "no_show"):
        raise ApiError(
            code="STATUS_INCOMPATIVEL",
            message=f"Compromisso está '{ap.status}' — não dá para reagendar.",
            hint="Crie um novo agendamento com POST /appointments.",
            status_code=409,
        )
    servico = carregar_servico(db, cred.org_id, ap.service_id)
    ap = reagendar(db, ap, servico, dados.novo_inicio, cred.ator, dados.motivo)
    corpo = _out(ap)
    idem.gravar(db, cred.org_id, request, corpo.model_dump(mode="json"), 200)
    db.commit()
    return corpo


@router.post(
    "/appointments/{appointment_id}/cancel",
    response_model=AppointmentOut,
    summary="Cancela e libera o slot imediatamente",
    description=(
        "Exige escopo agenda:cancel. Disparado por agente, exige confirmação humana: a "
        "primeira chamada (sem confirmation_token) devolve 409 CONFIRMACAO_NECESSARIA "
        "com a prévia e o token; repita com o token após o humano aprovar (expira em 5 "
        "min). O slot volta para a grade na hora — a fila de espera (RF-14) será "
        "notificada quando a etapa 7 ligar o job."
    ),
    responses=respostas(
        "NAO_ENCONTRADO",
        "CONFIRMACAO_NECESSARIA",
        "CONFIRMACAO_INVALIDA",
        "CONFIRMACAO_EXPIRADA",
    ),
    openapi_extra=operacao("agenda:cancel", idempotente=True),
)
def cancelar(
    appointment_id: UUID,
    dados: CancelIn,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:cancel")
    if repetida := idem.buscar(db, cred.org_id, request):
        return repetida
    ap = _carregar(db, cred, appointment_id)
    if ap.status == "cancelado":
        return _out(ap)  # idempotente por natureza
    if cred.ator == "agente":
        if dados.confirmation_token is None:
            raise ApiError(
                code="CONFIRMACAO_NECESSARIA",
                message="Cancelamento é irreversível e exige confirmação humana.",
                hint=(
                    "Mostre a prévia ao humano e, com o OK, repita esta chamada com o "
                    "confirmation_token do payload."
                ),
                status_code=409,
                extra={
                    "previa": {
                        "compromisso": str(ap.id),
                        "cliente": ap.cliente_nome,
                        "horario": label_humano(ap.periodo.lower),
                    },
                    "confirmation_token": confirmacao.gerar_token("cancel", ap.id),
                },
            )
        confirmacao.validar_token(dados.confirmation_token, "cancel", ap.id)
    anterior = ap.periodo
    ap.status = "cancelado"
    _historico(db, ap, "cancelado", de=anterior, origem=cred.ator, motivo=dados.motivo)
    _evento(db, ap, "agenda.appointment.canceled")
    corpo = _out(ap)
    idem.gravar(db, cred.org_id, request, corpo.model_dump(mode="json"), 200)
    db.commit()
    return corpo


@router.post(
    "/appointments/{appointment_id}/confirm",
    response_model=AppointmentOut,
    summary="Marca o compromisso como confirmado pelo cliente",
    description="Use quando o cliente responder 'sim' à confirmação. Só compromissos 'agendado' aceitam.",
    responses=respostas("NAO_ENCONTRADO", "STATUS_INCOMPATIVEL"),
    openapi_extra=operacao("agenda:write"),
)
def confirmar(
    appointment_id: UUID,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:write")
    ap = _carregar(db, cred, appointment_id)
    if ap.status != "agendado":
        raise ApiError(
            code="STATUS_INCOMPATIVEL",
            message=f"Compromisso está '{ap.status}' — só 'agendado' pode ser confirmado.",
            hint="Nada a fazer se já está confirmado; senão, verifique o compromisso certo.",
            status_code=409,
        )
    ap.status = "confirmado"
    _historico(db, ap, "confirmado", origem=cred.ator)
    db.commit()
    return _out(ap)


@router.post(
    "/appointments/{appointment_id}/no-show",
    response_model=AppointmentOut,
    summary="Registra falta do cliente (alimenta o histórico de risco — IA-03)",
    responses=respostas("NAO_ENCONTRADO"),
    openapi_extra=operacao("agenda:write"),
)
def no_show(
    appointment_id: UUID,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:write")
    ap = _carregar(db, cred, appointment_id)
    ap.status = "no_show"
    _historico(db, ap, "no_show", origem=cred.ator)
    db.commit()
    return _out(ap)


@router.get(
    "/appointments",
    response_model=list[AppointmentOut],
    summary="Lista compromissos por data e recurso",
    description="Todos os status, na ordem do dia. Para checar disponibilidade use GET /slots.",
    responses=respostas(),
    openapi_extra=operacao("agenda:read"),
)
def listar(
    data: date = Query(alias="date"),
    resource_id: UUID | None = Query(default=None, alias="resource"),
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> list[AppointmentOut]:
    exigir_escopo(cred, "agenda:read")
    dia_ini = datetime.combine(data, datetime.min.time(), tzinfo=TZ)
    dia_fim = dia_ini + timedelta(days=1)
    from sqlalchemy.dialects.postgresql import Range

    q = select(Appointment).where(
        Appointment.org_id == cred.org_id,
        Appointment.periodo.overlaps(Range(dia_ini, dia_fim)),
    )
    if resource_id:
        q = q.where(Appointment.resource_id == resource_id)
    return [_out(a) for a in db.scalars(q.order_by(Appointment.periodo))]


@router.get(
    "/agenda/day",
    response_model=AgendaDiaOut,
    summary="Agenda do dia, narrada para o agente",
    description=(
        "Visão consolidada em linguagem clara: compromissos com status e risco, na "
        "ordem do dia. Use para responder 'como está meu dia?' — não para checar "
        "disponibilidade (use GET /slots)."
    ),
    responses=respostas(),
    openapi_extra=operacao("agenda:read"),
)
def agenda_do_dia(
    data: date = Query(alias="date"),
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> dict:
    exigir_escopo(cred, "agenda:read")
    compromissos = listar(data=data, resource_id=None, cred=cred, db=db)
    linhas = [
        f"{c.label_humano} — {c.cliente_nome} ({c.status}"
        + (f", risco de falta {c.risco_no_show}" if c.risco_no_show else "")
        + ")"
        for c in compromissos
    ]
    return {
        "data": data.isoformat(),
        "total": len(compromissos),
        "narrativa": "\n".join(linhas) or "Nenhum compromisso neste dia.",
        "compromissos": [c.model_dump(mode="json") for c in compromissos],
    }


@router.get(
    "/appointments/{appointment_id}/history",
    response_model=list[HistoricoOut],
    summary="Histórico de alterações do compromisso (quem, quando, por quê)",
    responses=respostas("NAO_ENCONTRADO"),
    openapi_extra=operacao("agenda:read"),
)
def historico(
    appointment_id: UUID,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
) -> list[dict]:
    exigir_escopo(cred, "agenda:read")
    _carregar(db, cred, appointment_id)  # 404 se não é da org
    linhas = db.scalars(
        select(AppointmentHistory)
        .where(AppointmentHistory.appointment_id == appointment_id)
        .order_by(AppointmentHistory.em)
    ).all()
    return [
        {
            "acao": h.acao,
            "de": h.de.lower.isoformat() if h.de else None,
            "para": h.para.lower.isoformat() if h.para else None,
            "origem": h.origem,
            "motivo": h.motivo,
            "em": h.em.isoformat(),
        }
        for h in linhas
    ]
