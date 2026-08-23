from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Default "prod" de propósito: `dev_mode` libera X-Org-Id cru como
    # credencial, e a API é publicada na internet. Um deploy que esqueça
    # APP_ENV no .env não pode virar porta aberta — falhar fechado é o padrão.
    app_env: str = "prod"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/agenda"

    # Credencial service-to-service: só os serviços do programa chamam o canal
    # (nunca o navegador — `00` §4.8 / PRD §11).
    canal_service_key: str = ""

    # Chave Fernet para cifrar credenciais de driver no banco (write-only na API)
    canal_crypto_key: str = ""

    # Janela de sessão do WhatsApp: inbound do cliente abre 24h de resposta livre
    sessao_horas: int = 24

    # Base da URL de webhook que o DRIVER usa para alcançar o canal.
    # Driver self-host (Evolution) chama pela rede interna do Docker...
    webhook_base_url: str = "http://canal-service:8000"
    # ...driver de nuvem (Telegram, Z-API) precisa de HTTPS público. Só o
    # caminho /webhooks/canal/ é exposto — o resto do canal continua fechado.
    webhook_base_url_publica: str = ""

    # Para onde o inbound normalizado segue (PRD §9.1): o agente/orquestrador.
    # Vazio = só registra (comportamento anterior). O canal não pensa — entrega.
    orquestrador_url: str = ""
    orquestrador_key: str = ""

    @property
    def dev_mode(self) -> bool:
        return self.app_env != "prod"


@lru_cache
def settings() -> Settings:
    return Settings()
