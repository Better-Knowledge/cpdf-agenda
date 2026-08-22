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

from . import canal_client
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


def criar_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(processar_lembretes, "interval", minutes=5, id="lembretes")
    return scheduler
