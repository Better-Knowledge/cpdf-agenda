# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""RF-14 — fila de espera.

A regra que define o desenho: **sem hold**. Enquanto a oferta está de pé, o
slot continua livre na grade e qualquer pessoa pode agendá-lo — quem
confirmar primeiro leva, e a mensagem de oferta diz isso com todas as
letras. Segurar o horário para alguém que talvez não responda transformaria
a fila num jeito de piorar a agenda.

O aceite não tem caminho privilegiado: passa pelo mesmo `criar_appointment`
e pela mesma constraint do banco (RF-04). Se perdeu a corrida, o cliente
recebe as 3 alternativas mais próximas, como qualquer outro conflito.
"""

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.orm import Session

from .config import settings
from .models import Service, WaitlistEntry
from .tempo import agora_utc, label_humano

log = logging.getLogger("agenda.fila")

# Status que ainda esperam alguma coisa da fila
ABERTOS = ("aguardando", "ofertado")


def janela_de_aceite() -> timedelta:
    return timedelta(minutes=settings().fila_janela_aceite_min)


def expirar_ofertas_vencidas(db: Session, org_id: uuid.UUID | None = None) -> list[WaitlistEntry]:
    """Oferta sem resposta na janela volta para o fim da vez: a entrada
    expira e o próximo da fila passa a poder ser chamado."""
    agora = agora_utc()
    q = select(WaitlistEntry).where(
        WaitlistEntry.status == "ofertado", WaitlistEntry.expira_em <= agora
    )
    if org_id is not None:
        q = q.where(WaitlistEntry.org_id == org_id)
    vencidas = list(db.scalars(q))
    for entrada in vencidas:
        entrada.status = "expirado"
        log.info("oferta da fila %s expirou sem resposta", entrada.id)
    return vencidas


def candidatas(
    db: Session, org_id: uuid.UUID, service_id: uuid.UUID, resource_id: uuid.UUID,
    inicio: datetime, fim: datetime,
) -> list[WaitlistEntry]:
    """Quem está esperando por um horário compatível com o slot liberado.

    Compatível = mesmo serviço, recurso livre (ou sem exigência de recurso) e
    janela desejada que contém o horário. Ordem de chegada — a fila é fila.
    """
    periodo = Range(inicio, fim)
    return list(
        db.scalars(
            select(WaitlistEntry)
            .where(
                WaitlistEntry.org_id == org_id,
                WaitlistEntry.service_id == service_id,
                WaitlistEntry.status == "aguardando",
                WaitlistEntry.janela_desejada.contains(periodo),
                (WaitlistEntry.resource_id.is_(None))
                | (WaitlistEntry.resource_id == resource_id),
            )
            .order_by(WaitlistEntry.created_at)
        )
    )


def montar_oferta(
    entrada: WaitlistEntry, servico: Service, inicio: datetime
) -> dict[str, str]:
    """Variáveis do template `fila_oferta`. O texto do template deixa claro
    que não há reserva — quem confirmar primeiro leva."""
    return {
        "nome": entrada.cliente_nome,
        "servico": servico.nome,
        "data_hora": label_humano(inicio),
        "minutos": str(settings().fila_janela_aceite_min),
    }


def marcar_ofertada(
    entrada: WaitlistEntry, resource_id: uuid.UUID, inicio: datetime, fim: datetime
) -> None:
    agora = agora_utc()
    entrada.status = "ofertado"
    entrada.ofertado_em = agora
    entrada.expira_em = agora + janela_de_aceite()
    # a janela desejada é ampla ("quinta à tarde"); a oferta é um horário
    # exato num recurso exato — é isso que o aceite agenda.
    entrada.slot_ofertado = Range(inicio, fim)
    entrada.resource_ofertado = resource_id


def slot_ainda_livre(db: Session, resource_id: uuid.UUID, inicio: datetime, fim: datetime) -> bool:
    """Sem hold: entre a oferta e o aceite, qualquer um pode ter agendado."""
    from .models import Appointment

    conflito = db.scalar(
        select(Appointment).where(
            Appointment.resource_id == resource_id,
            Appointment.status.in_(("agendado", "confirmado")),
            Appointment.periodo.overlaps(Range(inicio, fim)),
        )
    )
    return conflito is None


def ja_ofertado(db: Session, org_id: uuid.UUID, inicio: datetime, fim: datetime) -> bool:
    """Já existe oferta em aberto para este horário?

    Sem esta guarda, duas chamadas próximas (o gatilho do cancelamento e o
    job de expiração, por exemplo) ofereceriam o MESMO horário a duas
    pessoas ao mesmo tempo — e a fila deixaria de ser uma fila.
    """
    aberta = db.scalar(
        select(WaitlistEntry).where(
            WaitlistEntry.org_id == org_id,
            WaitlistEntry.status == "ofertado",
            WaitlistEntry.expira_em > agora_utc(),
            WaitlistEntry.slot_ofertado.overlaps(Range(inicio, fim)),
        )
    )
    return aberta is not None


def ofertar_slot(
    db: Session,
    org_id: uuid.UUID,
    servico: Service,
    resource_id: uuid.UUID,
    inicio: datetime,
    fim: datetime,
    ignorar: set[uuid.UUID] | None = None,
) -> WaitlistEntry | None:
    """Oferece o slot ao primeiro da fila compatível. Devolve a entrada
    ofertada (já marcada) ou None se não havia ninguém esperando.

    Quem envia a mensagem é o chamador — esta função só decide e registra,
    para que a transação feche antes de qualquer I/O de rede.
    """
    if not slot_ainda_livre(db, resource_id, inicio, fim):
        return None
    if ja_ofertado(db, org_id, inicio, fim):
        return None  # a vez é de um por vez
    fila = candidatas(db, org_id, servico.id, resource_id, inicio, fim)
    for entrada in fila:
        if ignorar and entrada.id in ignorar:
            continue
        marcar_ofertada(entrada, resource_id, inicio, fim)
        log.info(
            "slot %s ofertado para %s (fila %s)",
            label_humano(inicio), entrada.cliente_telefone, entrada.id,
        )
        return entrada
    return None
