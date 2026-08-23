from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"

    # Quem pode entregar inbound aqui (o canal-service).
    agente_service_key: str = ""

    # As duas APIs que o agente consome — nunca o banco, nunca o WhatsApp direto.
    agenda_service_url: str = "http://agenda-service:8000"
    agenda_service_key: str = ""
    canal_service_url: str = "http://canal-service:8000"
    canal_service_key: str = ""

    # LLM da classificação de intenção (IA-04). Sem chave, o agente usa só as
    # regras determinísticas — e o que não bate vai para o humano.
    anthropic_api_key: str = ""
    modelo: str = "claude-haiku-4-5-20251001"

    @property
    def dev_mode(self) -> bool:
        return self.app_env != "prod"


@lru_cache
def settings() -> Settings:
    return Settings()
