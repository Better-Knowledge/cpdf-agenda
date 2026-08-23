"""Driver Telegram Bot API — o caminho mais curto para ver o produto rodando.

Por que ele existe no programa: WhatsApp não-oficial exige número dedicado,
chip, pareamento por QR e aceita risco de ban. Um bot de Telegram sai do
BotFather em trinta segundos, não tem janela de 24h imposta por política e
pode ser testado por qualquer pessoa da turma no próprio celular. É o mesmo
contrato de driver — a prova de que trocar de canal é configuração.

Credenciais esperadas (cifradas em channel_configs):
  { "bot_token": "123456:ABC-DEF..." }

**Endereço do cliente:** o Telegram não usa telefone — usa `chat_id`. O canal
grava `tg:<chat_id>` no campo `telefone`, que na prática é "endereço do
cliente neste canal": `+5511...` no WhatsApp, `tg:...` aqui. O prefixo torna
a origem óbvia e nunca colide com E.164.
"""

from datetime import UTC, datetime
from typing import Any

import httpx

from .base import DriverCanal, ErroDriver, EstadoConexao, MensagemInbound, ResultadoEnvio

BASE = "https://api.telegram.org"
PREFIXO = "tg:"


def endereco(chat_id: int | str) -> str:
    """chat_id do Telegram → endereço do cliente no canal."""
    return f"{PREFIXO}{chat_id}"


class DriverTelegram(DriverCanal):
    nome = "telegram"
    # Não-oficial no sentido do programa: template renderizado sai como texto.
    # (A regra template-first continua valendo — ela é invariante nossa, não da Meta.)
    suporta_texto_livre_ativo = True

    def _chamar(self, credenciais, metodo_api: str, corpo: dict | None = None) -> dict[str, Any]:
        base = credenciais.get("base_url", BASE).rstrip("/")
        url = f"{base}/bot{credenciais['bot_token']}/{metodo_api}"
        try:
            resposta = self.http.post(url, json=corpo or {})
        except httpx.HTTPError as e:
            raise ErroDriver(f"telegram inacessível: {e}", retryable=True) from e
        if resposta.status_code >= 500:
            raise ErroDriver(f"telegram respondeu {resposta.status_code}", retryable=True)
        corpo_resposta = resposta.json() if resposta.content else {}
        if resposta.status_code >= 400 or not corpo_resposta.get("ok", False):
            descricao = corpo_resposta.get("description", resposta.text[:200])
            # 401/404 aqui é quase sempre token errado — não adianta repetir
            raise ErroDriver(f"telegram recusou {metodo_api}: {descricao}", retryable=False)
        return corpo_resposta.get("result") or {}

    def enviar_texto(self, credenciais, telefone, texto) -> ResultadoEnvio:
        chat_id = telefone.removeprefix(PREFIXO)
        resultado = self._chamar(
            credenciais,
            "sendMessage",
            {"chat_id": chat_id, "text": texto, "disable_web_page_preview": True},
        )
        # message_id é único por CHAT, não global — a chave de idempotência
        # do canal é (driver, driver_message_id), então qualifica com o chat.
        return ResultadoEnvio(driver_message_id=f"{chat_id}:{resultado.get('message_id')}")

    def enviar_template_oficial(self, credenciais, telefone, template_nome, variaveis):
        raise ErroDriver(
            "telegram não tem templates oficiais — renderize e use texto", retryable=False
        )

    def normalizar_inbound(self, payload: dict[str, Any]) -> MensagemInbound | None:
        mensagem = payload.get("message") or payload.get("edited_message")
        if not mensagem:
            return None  # callback_query, edição de canal, etc. — fora do escopo
        remetente = mensagem.get("from") or {}
        if remetente.get("is_bot"):
            return None
        texto = mensagem.get("text")
        if not texto:
            return None  # foto, áudio, sticker: sem texto, nada a interpretar
        chat_id = (mensagem.get("chat") or {}).get("id")
        if chat_id is None:
            return None
        data = mensagem.get("date")
        return MensagemInbound(
            # O update do Telegram não identifica o bot: a instância vem da URL
            # do webhook (ver routers/webhooks.py), que é única por organização.
            instancia="",
            telefone=endereco(chat_id),
            texto=texto,
            message_id=f"{chat_id}:{mensagem.get('message_id')}",
            timestamp=datetime.fromtimestamp(int(data), tz=UTC) if data else None,
        )

    def conectar(self, credenciais, webhook_url) -> EstadoConexao:
        bot = self._chamar(credenciais, "getMe")
        self._chamar(
            credenciais,
            "setWebhook",
            {
                "url": webhook_url,
                # Telegram devolve este segredo no header a cada update — é a
                # verificação idiomática, melhor que segredo só na URL.
                "secret_token": credenciais.get("webhook_secret", ""),
                "allowed_updates": ["message"],
                "drop_pending_updates": True,
            },
        )
        usuario = bot.get("username")
        return EstadoConexao(
            estado="conectado",
            detalhe=f"@{usuario} pronto — mande /start para o bot e escreva" if usuario else None,
        )

    def estado_conexao(self, credenciais) -> EstadoConexao:
        info = self._chamar(credenciais, "getWebhookInfo")
        if not info.get("url"):
            return EstadoConexao(
                estado="desconectado",
                detalhe="webhook não configurado — use Conectar",
            )
        erro = info.get("last_error_message")
        return EstadoConexao(
            estado="conectado",
            detalhe=f"último erro do Telegram: {erro}" if erro else None,
        )
