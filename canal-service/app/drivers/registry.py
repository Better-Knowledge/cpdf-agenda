# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Trocar de driver é configuração (channel_configs.driver), nunca código.

A mesma suíte de testes roda em todos os drivers implementados — teste de
aceite do RF-10.
"""

import httpx

from ..errors import ApiError
from .base import DriverCanal
from .evolution import DriverEvolution
from .meta import DriverMeta
from .telegram import DriverTelegram
from .zapi import DriverZapi

DRIVERS: dict[str, type[DriverCanal]] = {
    "evolution": DriverEvolution,
    "zapi": DriverZapi,
    "telegram": DriverTelegram,
    "meta": DriverMeta,
}


def obter_driver(nome: str, http: httpx.Client | None = None) -> DriverCanal:
    classe = DRIVERS.get(nome)
    if classe is None:
        raise ApiError(
            code="DRIVER_DESCONHECIDO",
            message=f"Driver '{nome}' não existe.",
            hint="Use evolution, zapi, telegram ou meta (meta é extensão guiada).",
        )
    return classe(http=http)
