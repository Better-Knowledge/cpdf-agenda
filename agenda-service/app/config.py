from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/agenda"

    supabase_jwt_secret: str = ""
    agent_api_keys: dict[str, str] = {}  # chave estática → org_id (fase 1 do conector)

    canal_service_url: str = "http://canal-service:8000"
    canal_service_key: str = ""

    tasks_service_url: str = ""
    tasks_service_key: str = ""

    # Regras de agendamento (padrões do PRD; por-org fica para a etapa de configurações)
    granularidade_min: int = 30
    antecedencia_minima_min: int = 60
    janela_maxima_dias: int = 60

    @property
    def dev_mode(self) -> bool:
        return self.app_env != "prod"


@lru_cache
def settings() -> Settings:
    return Settings()
