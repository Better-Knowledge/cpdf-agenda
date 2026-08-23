from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/agenda"

    # Credencial service-to-service: só os serviços do programa chamam o canal
    # (nunca o navegador — `00` §4.8 / PRD §11).
    canal_service_key: str = ""

    # Chave Fernet para cifrar credenciais de driver no banco (write-only na API)
    canal_crypto_key: str = ""

    # Janela de sessão do WhatsApp: inbound do cliente abre 24h de resposta livre
    sessao_horas: int = 24

    # Base da URL de webhook que o DRIVER usa para alcançar o canal. Para o
    # Evolution self-host é o endereço interno do Docker; um driver de nuvem
    # exigiria expor /webhooks/canal/* publicamente (etapa da demo Z-API).
    webhook_base_url: str = "http://canal-service:8000"

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
