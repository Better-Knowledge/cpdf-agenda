# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Driver Z-API (instância assinada).

Credenciais esperadas (cifradas em channel_configs):
  { "instancia": "<id>", "token": "...", "client_token": "..." }
"""

from datetime import UTC, datetime
from typing import Any

import httpx

from .base import DriverCanal, ErroDriver, MensagemInbound, ResultadoEnvio

BASE = "https://api.z-api.io"


class DriverZapi(DriverCanal):
    nome = "zapi"
    suporta_texto_livre_ativo = True

    def enviar_texto(self, credenciais, telefone, texto) -> ResultadoEnvio:
        url = (
            f"{credenciais.get('base_url', BASE).rstrip('/')}"
            f"/instances/{credenciais['instancia']}/token/{credenciais['token']}/send-text"
        )
        try:
            resposta = self.http.post(
                url,
                json={"phone": telefone.lstrip("+"), "message": texto},
                headers={"Client-Token": credenciais["client_token"]},
            )
        except httpx.HTTPError as e:
            raise ErroDriver(f"z-api inacessível: {e}", retryable=True) from e
        if resposta.status_code >= 500:
            raise ErroDriver(f"z-api respondeu {resposta.status_code}", retryable=True)
        if resposta.status_code >= 400:
            raise ErroDriver(f"z-api recusou o envio: {resposta.text[:200]}", retryable=False)
        corpo = resposta.json()
        return ResultadoEnvio(driver_message_id=corpo.get("messageId") or corpo.get("zaapId"))

    def enviar_template_oficial(self, credenciais, telefone, template_nome, variaveis):
        raise ErroDriver("z-api não tem templates oficiais — renderize e use texto", retryable=False)

    def normalizar_inbound(self, payload: dict[str, Any]) -> MensagemInbound | None:
        if payload.get("fromMe") or payload.get("isStatusReply"):
            return None
        texto = (payload.get("text") or {}).get("message")
        if not texto:
            return None
        ts = payload.get("momment") or payload.get("moment")
        return MensagemInbound(
            instancia=str(payload.get("instanceId", "")),
            telefone="+" + str(payload.get("phone", "")),
            texto=texto,
            message_id=str(payload.get("messageId", "")),
            timestamp=datetime.fromtimestamp(int(ts) / 1000, tz=UTC) if ts else None,
        )
