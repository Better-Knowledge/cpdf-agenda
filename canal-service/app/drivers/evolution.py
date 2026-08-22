"""Driver Evolution API (self-host no VPS — custo zero, QR code ao vivo).

Credenciais esperadas (cifradas em channel_configs):
  { "server_url": "http://evolution:8080", "instancia": "minha-org", "apikey": "..." }
"""

from datetime import UTC, datetime
from typing import Any

import httpx

from .base import DriverCanal, ErroDriver, MensagemInbound, ResultadoEnvio


class DriverEvolution(DriverCanal):
    nome = "evolution"
    suporta_texto_livre_ativo = True  # não-oficial: template renderizado sai como texto

    def enviar_texto(self, credenciais, telefone, texto) -> ResultadoEnvio:
        url = f"{credenciais['server_url'].rstrip('/')}/message/sendText/{credenciais['instancia']}"
        try:
            resposta = self.http.post(
                url,
                json={"number": telefone.lstrip("+"), "text": texto},
                headers={"apikey": credenciais["apikey"]},
            )
        except httpx.HTTPError as e:
            raise ErroDriver(f"evolution inacessível: {e}", retryable=True) from e
        if resposta.status_code >= 500:
            raise ErroDriver(f"evolution respondeu {resposta.status_code}", retryable=True)
        if resposta.status_code >= 400:
            raise ErroDriver(f"evolution recusou o envio: {resposta.text[:200]}", retryable=False)
        corpo = resposta.json()
        return ResultadoEnvio(driver_message_id=(corpo.get("key") or {}).get("id"))

    def enviar_template_oficial(self, credenciais, telefone, template_nome, variaveis):
        raise ErroDriver("evolution não tem templates oficiais — renderize e use texto", retryable=False)

    def normalizar_inbound(self, payload: dict[str, Any]) -> MensagemInbound | None:
        # Evento messages.upsert da Evolution v2
        if payload.get("event") not in ("messages.upsert", "MESSAGES_UPSERT"):
            return None
        dados = payload.get("data") or {}
        chave = dados.get("key") or {}
        if chave.get("fromMe"):
            return None
        mensagem = dados.get("message") or {}
        texto = mensagem.get("conversation") or (
            (mensagem.get("extendedTextMessage") or {}).get("text")
        )
        if not texto:
            return None
        telefone = "+" + str(chave.get("remoteJid", "")).split("@")[0]
        ts = dados.get("messageTimestamp")
        return MensagemInbound(
            instancia=payload.get("instance", ""),
            telefone=telefone,
            texto=texto,
            message_id=chave.get("id", ""),
            timestamp=datetime.fromtimestamp(int(ts), tz=UTC) if ts else None,
        )
