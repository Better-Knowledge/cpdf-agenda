"""Driver Evolution API (self-host no VPS — custo zero, QR code ao vivo).

Credenciais esperadas (cifradas em channel_configs):
  { "server_url": "http://evolution:8080", "instancia": "minha-org", "apikey": "..." }
"""

from datetime import UTC, datetime
from typing import Any

import httpx

from .base import DriverCanal, ErroDriver, EstadoConexao, MensagemInbound, ResultadoEnvio

_ESTADOS = {"open": "conectado", "connecting": "aguardando_qr", "close": "desconectado"}


class DriverEvolution(DriverCanal):
    nome = "evolution"
    suporta_texto_livre_ativo = True  # não-oficial: template renderizado sai como texto

    def _chamar(self, credenciais, metodo: str, rota: str, corpo=None) -> dict[str, Any]:
        url = f"{credenciais['server_url'].rstrip('/')}{rota}"
        try:
            resposta = self.http.request(
                metodo, url, json=corpo, headers={"apikey": credenciais["apikey"]}
            )
        except httpx.HTTPError as e:
            raise ErroDriver(f"evolution inacessível: {e}", retryable=True) from e
        if resposta.status_code >= 500:
            raise ErroDriver(f"evolution respondeu {resposta.status_code}", retryable=True)
        if resposta.status_code >= 400:
            raise ErroDriver(
                f"evolution recusou {metodo} {rota}: {resposta.text[:200]}", retryable=False
            )
        return resposta.json() if resposta.content else {}

    def conectar(self, credenciais, webhook_url) -> EstadoConexao:
        instancia = credenciais["instancia"]
        # 1. Garante a instância (criar de novo é erro "already in use" — tolerado).
        try:
            self._chamar(
                credenciais,
                "POST",
                "/instance/create",
                {"instanceName": instancia, "qrcode": True, "integration": "WHATSAPP-BAILEYS"},
            )
        except ErroDriver as e:
            if e.retryable or "already in use" not in str(e):
                raise
        # 2. Aponta o webhook da instância para o canal (só MESSAGES_UPSERT).
        self._chamar(
            credenciais,
            "POST",
            f"/webhook/set/{instancia}",
            {
                "webhook": {
                    "enabled": True,
                    "url": webhook_url,
                    "events": ["MESSAGES_UPSERT"],
                    "byEvents": False,
                    "base64": False,
                }
            },
        )
        # 3. Pede a conexão: devolve QR para parear ou o estado, se já pareada.
        corpo = self._chamar(credenciais, "GET", f"/instance/connect/{instancia}")
        if corpo.get("base64"):
            return EstadoConexao(
                estado="aguardando_qr",
                qr_base64=corpo["base64"],
                detalhe="Escaneie o QR em WhatsApp > Aparelhos conectados.",
            )
        return self.estado_conexao(credenciais)

    def estado_conexao(self, credenciais) -> EstadoConexao:
        corpo = self._chamar(
            credenciais, "GET", f"/instance/connectionState/{credenciais['instancia']}"
        )
        cru = (corpo.get("instance") or {}).get("state", "")
        return EstadoConexao(estado=_ESTADOS.get(cru, "desconhecido"), detalhe=cru or None)

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
