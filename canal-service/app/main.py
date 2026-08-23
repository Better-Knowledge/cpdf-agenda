# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""canal-service — adapter de WhatsApp do programa (`00` §4.8).

Nasce no módulo 02 e é reutilizado pelos módulos 03 (pedidos) e 04
(cobrança). Só aceita chamadas service-to-service — nunca do navegador;
a exceção são os webhooks inbound dos drivers.
"""

import logging

from fastapi import FastAPI

from .config import settings
from .errors import instalar_handlers
from .routers import canal, health, webhooks

logging.basicConfig(level=settings().log_level)

app = FastAPI(
    title="Canal de WhatsApp — canal-service",
    version="0.1.0",
    description=(
        "Envio (template-first) e recebimento de mensagens, com drivers evolution/zapi "
        "implementados e meta como interface. Opt-out determinístico. Erros seguem "
        "`{code, message, hint, retryable}`."
    ),
)

instalar_handlers(app)
app.include_router(health.router)
app.include_router(canal.router)
app.include_router(webhooks.router)
