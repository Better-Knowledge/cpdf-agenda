"""Driver Meta Cloud API — interface pronta, implementação como extensão (aula).

O que a implementação exige (conteúdo do módulo, PRD §9.1):
- App Meta com verificação de negócio e número dedicado;
- Mensagem ATIVA só com template pré-aprovado (por isso todo template do
  canal já carrega o flag `aprovado_meta` — migrar é trocar driver e aprovar
  templates, não reescrever módulos);
- Webhook verificado por token (`hub.challenge`) + assinatura X-Hub-Signature-256;
- Custo por conversa/template registrado em channel_messages.custo.
"""

from typing import Any

from .base import DriverCanal, ErroDriver, MensagemInbound, ResultadoEnvio


class DriverMeta(DriverCanal):
    nome = "meta"
    suporta_texto_livre_ativo = False  # oficial: ativa exige template pré-aprovado

    def enviar_texto(self, credenciais, telefone, texto) -> ResultadoEnvio:
        raise NotImplementedError(
            "Extensão guiada do programa: enviar texto de sessão via "
            "POST /{phone_number_id}/messages (type=text)."
        )

    def enviar_template_oficial(self, credenciais, telefone, template_nome, variaveis):
        raise NotImplementedError(
            "Extensão guiada do programa: enviar template aprovado via "
            "POST /{phone_number_id}/messages (type=template)."
        )

    def normalizar_inbound(self, payload: dict[str, Any]) -> MensagemInbound | None:
        raise NotImplementedError(
            "Extensão guiada do programa: normalizar entry[].changes[].value.messages[]."
        )


# Reexporta para o registry manter um único ponto de import
__all__ = ["DriverMeta", "DriverCanal", "ErroDriver", "MensagemInbound", "ResultadoEnvio"]
