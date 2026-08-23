# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Jobs do VPS (APScheduler) — disparam com a máquina do aluno desligada.

Lembretes (RF-05): varre `reminders` vencidos a cada 5 min, janela de
tolerância de 15 min, idempotente (unique appointment_id+tipo + a chave de
idempotência no canal). Falha → retry até 3; esgotado, registra erro e
deixa tarefa manual (integração tasks-service na etapa 7).
"""

import logging
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from . import canal_client, fila, google_sync, ofertas
from . import risco as risco_no_show
from .db import SessionLocal, sessao_org, sessao_worker
from .models import Appointment, Reminder, Service
from .tempo import agora_utc, label_humano

log = logging.getLogger("agenda.jobs")

TOLERANCIA = timedelta(minutes=15)
MAX_TENTATIVAS = 3

TEMPLATE_POR_TIPO = {
    "confirmacao": "confirmacao",
    "lembrete_24h": "lembrete_24h",
    "lembrete_2h": "lembrete_2h",
    "risco_alto": "risco_alto",
}


def processar_lembretes() -> None:
    agora = agora_utc()
    with SessionLocal() as db:
        sessao_worker(db)  # varredura cruza orgs; o envio abaixo é por org
        pendentes = db.scalars(
            select(Reminder)
            .where(
                Reminder.enviado_em.is_(None),
                Reminder.agendado_para <= agora,
                Reminder.agendado_para >= agora - TOLERANCIA,
                Reminder.tentativas < MAX_TENTATIVAS,
            )
            .execution_options(populate_existing=True)
        ).all()

    for lembrete in pendentes:
        with SessionLocal() as db:
            sessao_org(db, lembrete.org_id)
            r = db.get(Reminder, lembrete.id)
            if r is None or r.enviado_em is not None:
                continue
            ap = db.get(Appointment, r.appointment_id)
            servico = db.get(Service, ap.service_id) if ap else None
            if ap is None or servico is None or ap.status in ("cancelado", "realizado"):
                r.enviado_em = agora_utc()  # nada a enviar; encerra o lembrete
                r.erro = "compromisso encerrado antes do envio"
                db.commit()
                continue
            # IA-03: o lembrete de 24h é o segundo gatilho do cálculo — até aqui
            # o cliente pode ter faltado em outro compromisso.
            if r.tipo == "lembrete_24h":
                if risco_no_show.aplicar(db, ap) == "alto":
                    agendar_lembrete_de_risco(db, ap)

            try:
                resultado = canal_client.enviar_template(
                    org_id=ap.org_id,
                    destinatario=ap.cliente_telefone,
                    template_nome=TEMPLATE_POR_TIPO[r.tipo],
                    variaveis={
                        "nome": ap.cliente_nome,
                        "servico": servico.nome,
                        "data_hora": label_humano(ap.periodo.lower),
                    },
                    idempotency_key=f"reminder-{r.id}",
                )
                if resultado["status_code"] < 400:
                    r.enviado_em = agora_utc()
                    r.canal_message_id = resultado.get("message_id")
                else:
                    # opt-out ou template ausente: o lembrete morre com log e
                    # a tarefa manual avisa o humano (tasks-service, etapa 7)
                    r.tentativas = MAX_TENTATIVAS
                    r.erro = f"{resultado.get('code')}: {resultado.get('message')}"
                    log.warning("lembrete %s recusado pelo canal: %s", r.id, r.erro)
            except canal_client.CanalIndisponivel as e:
                r.tentativas += 1
                r.erro = str(e)
                log.warning("canal indisponível para lembrete %s (%s)", r.id, e)
            db.commit()


def agendar_lembrete_de_risco(db, ap: Appointment) -> None:
    """Risco alto ganha UM lembrete extra pedindo confirmação explícita
    (IA-03). Nunca cancela nada — só pede resposta.

    A unique (appointment_id, tipo) faz a idempotência: recalcular o risco
    várias vezes não gera enxurrada de mensagem.
    """
    ja_existe = db.scalar(
        select(Reminder).where(
            Reminder.appointment_id == ap.id, Reminder.tipo == "risco_alto"
        )
    )
    if ja_existe is not None:
        return
    db.add(
        Reminder(
            org_id=ap.org_id,
            appointment_id=ap.id,
            tipo="risco_alto",
            agendado_para=agora_utc(),
        )
    )
    log.info("risco alto em %s — lembrete extra de confirmação agendado", ap.id)


def processar_fila() -> None:
    """RF-14: oferta sem resposta na janela expira e o horário passa ao
    próximo da fila — se ainda estiver livre, porque não houve reserva."""
    with SessionLocal() as db:
        sessao_worker(db)
        vencidas = [
            (e.org_id, e.service_id, e.resource_ofertado, e.slot_ofertado)
            for e in fila.expirar_ofertas_vencidas(db)
        ]
        db.commit()

    for org_id, service_id, resource_id, slot in vencidas:
        if slot is None or resource_id is None:
            continue  # oferta antiga sem registro do que foi proposto
        ofertas.ofertar_slot_liberado(org_id, service_id, resource_id, slot.lower, slot.upper)


def processar_google() -> None:
    """RF-12: push assíncrono para o Google Calendar.

    Falha na API do Google não bloqueia agendamento — é este job que absorve
    a indisponibilidade, com backoff e no máximo 5 tentativas por evento.
    """
    try:
        google_sync.processar_pendentes()
    except Exception:  # um job não pode derrubar o scheduler
        log.exception("falha inesperada no push do Google Calendar")


def criar_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(processar_lembretes, "interval", minutes=5, id="lembretes")
    scheduler.add_job(processar_fila, "interval", minutes=1, id="fila")
    scheduler.add_job(processar_google, "interval", minutes=1, id="google")
    return scheduler
