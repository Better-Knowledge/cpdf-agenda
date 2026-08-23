# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Envio das ofertas da fila (RF-14) — fora do caminho da resposta HTTP.

Separado do router de propósito: quem cancela um horário não deve esperar a
mensagem do canal sair para receber o 200. A oferta segue em background e,
se o canal estiver fora do ar, a fila continua íntegra — a entrada volta
para 'aguardando' e o job tenta de novo.
"""

import logging
import uuid
from datetime import datetime

from . import canal_client, fila
from .db import SessionLocal, sessao_org
from .models import Service, WaitlistEntry

log = logging.getLogger("agenda.fila")

TEMPLATE_OFERTA = "fila_oferta"


def _tentar_enviar(org_id, telefone, variaveis, entrada_id) -> tuple[bool, str]:
    """(enviou?, motivo). Distinguir permanente de temporário importa: opt-out
    nunca vai funcionar para esse cliente, enquanto canal fora do ar volta."""
    try:
        resultado = canal_client.enviar_template(
            org_id=org_id,
            destinatario=telefone,
            template_nome=TEMPLATE_OFERTA,
            variaveis=variaveis,
            idempotency_key=f"fila-oferta-{entrada_id}",
        )
    except canal_client.CanalIndisponivel as e:
        return False, f"TEMPORARIO: {e}"
    if resultado["status_code"] < 400:
        return True, ""
    return False, f"{resultado.get('code')}: {resultado.get('message')}"


def _devolver_a_fila(org_id: uuid.UUID, entrada_id: uuid.UUID) -> None:
    """A oferta não chegou: ninguém foi avisado, então a vez não pode ser
    consumida. A entrada volta para 'aguardando' como se nada tivesse
    acontecido."""
    with SessionLocal() as db:
        sessao_org(db, org_id)
        entrada = db.get(WaitlistEntry, entrada_id)
        if entrada is not None and entrada.status == "ofertado":
            entrada.status = "aguardando"
            entrada.ofertado_em = entrada.expira_em = None
            entrada.slot_ofertado = entrada.resource_ofertado = None
            db.commit()


def ofertar_slot_liberado(
    org_id: uuid.UUID,
    service_id: uuid.UUID,
    resource_id: uuid.UUID,
    inicio: datetime,
    fim: datetime,
) -> uuid.UUID | None:
    """Um horário vagou: oferece ao primeiro da fila que consiga ser avisado.

    Cada transação fecha ANTES do envio — se a mensagem falhar, a entrada
    volta para 'aguardando' sem segurar o horário de ninguém. Quem não pode
    ser avisado (opt-out) é pulado NESTA rodada, senão ele travaria a fila
    inteira para sempre; a entrada continua lá para contato humano.
    """
    pulados: set[uuid.UUID] = set()
    while True:
        with SessionLocal() as db:
            sessao_org(db, org_id)
            servico = db.get(Service, service_id)
            if servico is None:
                return None
            entrada = fila.ofertar_slot(
                db, org_id, servico, resource_id, inicio, fim, ignorar=pulados
            )
            if entrada is None:
                return None  # ninguém esperando (ou o slot já foi tomado)
            variaveis = fila.montar_oferta(entrada, servico, inicio)
            entrada_id, telefone = entrada.id, entrada.cliente_telefone
            db.commit()

        enviou, motivo = _tentar_enviar(org_id, telefone, variaveis, entrada_id)
        if enviou:
            log.info("oferta da fila %s enviada para %s", entrada_id, telefone)
            return entrada_id

        _devolver_a_fila(org_id, entrada_id)
        if motivo.startswith("TEMPORARIO"):
            # Canal fora do ar: tentar o próximo daria no mesmo.
            log.warning("oferta da fila %s adiada (%s)", entrada_id, motivo)
            return None
        log.warning(
            "oferta da fila %s não pôde ser avisada (%s) — passando ao próximo",
            entrada_id, motivo,
        )
        pulados.add(entrada_id)
