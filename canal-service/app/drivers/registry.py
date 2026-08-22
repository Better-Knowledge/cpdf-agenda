"""Trocar de driver é configuração (channel_configs.driver), nunca código.

A mesma suíte de testes roda nos dois drivers implementados — teste de
aceite do RF-10.
"""

import httpx

from ..errors import ApiError
from .base import DriverCanal
from .evolution import DriverEvolution
from .meta import DriverMeta
from .zapi import DriverZapi

DRIVERS: dict[str, type[DriverCanal]] = {
    "evolution": DriverEvolution,
    "zapi": DriverZapi,
    "meta": DriverMeta,
}


def obter_driver(nome: str, http: httpx.Client | None = None) -> DriverCanal:
    classe = DRIVERS.get(nome)
    if classe is None:
        raise ApiError(
            code="DRIVER_DESCONHECIDO",
            message=f"Driver '{nome}' não existe.",
            hint="Use evolution, zapi ou meta (meta é extensão guiada).",
        )
    return classe(http=http)
