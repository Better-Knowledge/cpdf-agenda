# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""RF-15 — Recorrência simples: série semanal/quinzenal, sem RRULE.

Cada ocorrência é um appointment próprio ligado à série (series_id) —
lembretes, confirmação e no-show funcionam por ocorrência sem caso especial.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .. import confirmacao
from .. import idempotency as idem
from ..auth import ESCOPO_OPERACAO, Credencial, credencial_atual, exigir_escopo
from ..booking import (
    _evento,
    _historico,
    carregar_servico,
    criar_appointment,
    gerar_ocorrencias,
    recursos_do_servico,
)
from ..contrato import operacao, respostas
from ..db import get_db
from ..errors import ApiError, NaoEncontrado
from ..models import Appointment, RecurrenceSeries
from ..schemas import (
    ConflitoOcorrencia,
    RecurrenceIn,
    RecurrenceOut,
    SerieCanceladaOut,
    SeriesCancelIn,
)
from ..tempo import TZ, label_humano
from .appointments import _exigir_titular, _out

router = APIRouter(tags=["recorrência"])


@router.post(
    "/appointments/recorrentes",
    response_model=RecurrenceOut,
    status_code=201,
    summary="Cria uma série recorrente ('toda terça às 10h até dezembro')",
    description=(
        "Série semanal ou quinzenal a partir de `inicio` (primeira ocorrência), com "
        "`ocorrencias` OU `fim_em`. Cada ocorrência vira um compromisso próprio com a "
        "mesma régua de lembretes. Ocorrência que cair em horário ocupado NÃO quebra a "
        "série: volta em `conflitos`, já com as 3 alternativas — ofereça-as ao cliente "
        "e agende com POST /appointments. Aceita Idempotency-Key."
    ),
    responses=respostas("NAO_ENCONTRADO", "DATA_SEM_FUSO", "TITULAR_DIVERGENTE"),
    openapi_extra=operacao("agenda:write", idempotente=True),
)
def criar_serie(
    dados: RecurrenceIn,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:write")
    if repetida := idem.buscar(db, cred.org_id, request, cred.titular):
        return repetida
    telefone = _exigir_titular(cred, dados.cliente_telefone)
    servico = carregar_servico(db, cred.org_id, dados.service_id)
    recursos = recursos_do_servico(db, servico)
    if dados.resource_id is not None:
        recursos = [r for r in recursos if r.id == dados.resource_id]
    if not recursos:
        raise NaoEncontrado("Recurso", str(dados.resource_id))
    recurso = recursos[0]  # série vive num único recurso

    inicio_local = dados.inicio.astimezone(TZ)
    serie = RecurrenceSeries(
        org_id=cred.org_id,
        service_id=servico.id,
        resource_id=recurso.id,
        frequencia=dados.frequencia,
        dia_semana=inicio_local.weekday(),
        hora_inicio=inicio_local.time(),
        fim_em=dados.fim_em,
        ocorrencias=dados.ocorrencias,
    )
    db.add(serie)
    db.flush()

    criadas, conflitos = [], []
    for quando in gerar_ocorrencias(
        dados.inicio, dados.frequencia, dados.ocorrencias, dados.fim_em
    ):
        try:
            ap = criar_appointment(
                db,
                cred.org_id,
                servico,
                recurso.id,
                quando,
                dados.cliente_nome,
                telefone,
                dados.origem,
                dados.observacoes,
                series_id=serie.id,
            )
            criadas.append(_out(ap, completo=cred.pode(ESCOPO_OPERACAO)))
        except ApiError as e:
            if e.code != "SLOT_INDISPONIVEL":
                raise
            # a série não quebra: a ocorrência fica pendente, com alternativas
            conflitos.append(
                ConflitoOcorrencia(
                    inicio=quando,
                    label_humano=label_humano(quando),
                    alternativas=e.extra.get("alternativas", []),
                )
            )

    corpo = RecurrenceOut(
        series_id=serie.id,
        frequencia=dados.frequencia,
        criadas=criadas,
        conflitos=conflitos,
    )
    idem.gravar(db, cred.org_id, request, corpo.model_dump(mode="json"), 201, cred.titular)
    db.commit()
    return corpo


@router.post(
    "/appointments/recorrentes/{series_id}/cancel",
    summary="Cancela TODAS as ocorrências futuras da série",
    description=(
        "Distinto de cancelar UMA ocorrência (POST /appointments/{id}/cancel — RF-06). "
        "Exige agenda:cancel. Disparado por agente, exige confirmação humana: a "
        "primeira chamada devolve 409 CONFIRMACAO_NECESSARIA com prévia e token. "
        "Ocorrências passadas ou já realizadas não mudam; os slots futuros voltam "
        "para a grade na hora. Exige também `agenda:operacao`: a série é entidade da "
        "operação, e cancelá-la inteira não é ato de atendimento."
    ),
    response_model=SerieCanceladaOut,
    responses=respostas(
        "NAO_ENCONTRADO",
        "CONFIRMACAO_NECESSARIA",
        "CONFIRMACAO_INVALIDA",
        "CONFIRMACAO_EXPIRADA",
    ),
    openapi_extra=operacao("agenda:cancel + agenda:operacao", idempotente=True),
)
def cancelar_serie(
    series_id: UUID,
    dados: SeriesCancelIn,
    request: Request,
    cred: Credencial = Depends(credencial_atual),
    db: Session = Depends(get_db),
):
    exigir_escopo(cred, "agenda:cancel")
    exigir_escopo(cred, "agenda:operacao")
    if repetida := idem.buscar(db, cred.org_id, request, cred.titular):
        return repetida
    serie = db.scalar(
        select(RecurrenceSeries).where(
            RecurrenceSeries.id == series_id, RecurrenceSeries.org_id == cred.org_id
        )
    )
    if serie is None:
        raise NaoEncontrado("Série", str(series_id))

    futuras = db.scalars(
        select(Appointment)
        .where(
            Appointment.series_id == series_id,
            Appointment.status.in_(("agendado", "confirmado")),
            text("lower(periodo) > now()"),
        )
        .order_by(Appointment.periodo)
    ).all()

    if cred.ator == "agente":
        if dados.confirmation_token is None:
            raise ApiError(
                code="CONFIRMACAO_NECESSARIA",
                message="Cancelar a série inteira é irreversível e exige confirmação humana.",
                hint=(
                    "Mostre a prévia ao humano e, com o OK, repita a chamada com o "
                    "confirmation_token do payload."
                ),
                status_code=409,
                extra={
                    "previa": {
                        "serie": str(serie.id),
                        "ocorrencias_futuras": len(futuras),
                        "proxima": label_humano(futuras[0].periodo.lower) if futuras else None,
                    },
                    "confirmation_token": confirmacao.gerar_token("cancel-series", serie.id),
                },
            )
        confirmacao.validar_token(dados.confirmation_token, "cancel-series", serie.id)

    for ap in futuras:
        anterior = ap.periodo
        ap.status = "cancelado"
        _historico(db, ap, "cancelado", de=anterior, origem=cred.ator, motivo=dados.motivo)
        _evento(db, ap, "agenda.appointment.canceled")
    serie.ativo = False

    corpo = {"series_id": str(serie.id), "canceladas": len(futuras)}
    idem.gravar(db, cred.org_id, request, corpo, 200, cred.titular)
    db.commit()
    return corpo
