from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "prod"
    log_level: str = "INFO"

    # A agenda é a única coisa que este serviço conhece. Ele não tem banco, não
    # tem estado e — de propósito — não tem credencial própria: ver `agenda.py`.
    agenda_service_url: str = "http://agenda-service:8000"

    # Proteção contra DNS rebinding do transporte MCP: os Host aceitos. Atrás do
    # Caddy é o domínio público (ex.: "mcp.suaempresa.com"). Vazio em produção
    # derruba a subida — o SDK, com a proteção ligada e a lista vazia, recusaria
    # toda requisição, e falhar na inicialização é melhor do que um serviço que
    # sobe e responde 421 a tudo.
    mcp_hosts_permitidos: list[str] = []

    @property
    def dev_mode(self) -> bool:
        return self.app_env != "prod"


@lru_cache
def settings() -> Settings:
    return Settings()
