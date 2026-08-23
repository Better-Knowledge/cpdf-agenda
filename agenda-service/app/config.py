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

    supabase_jwt_secret: str = ""
    # AGENT_API_KEYS (chave estática no ambiente → org) foi removida: escopo por
    # credencial e revogação sem redeploy exigem que a credencial viva no banco.
    # `app.admin_cli importar-env` migra as chaves antigas preservando o valor,
    # para que nenhum navegador precise ser deslogado.
    #
    # Credencial service-to-service legada. Só vale com ATENDIMENTO_ISOLADO
    # desligado — é a alavanca de rollback, não um caminho suportado.
    agenda_service_key: str = ""

    # RF-19 — segredo do token de sessão de atendimento. COMPARTILHADO com o
    # canal-service, que é quem cunha o token (é lá que o endereço do cliente é
    # provado). Vazio em produção derruba a emissão: melhor falhar do que
    # assinar com um segredo público.
    sessao_atendimento_secret: str = ""
    # Virada do isolamento (RF-19), agora LIGADA por padrão: `X-Service-Key`
    # não concede mais a organização inteira, e todo atendimento passa pelo
    # token de sessão que o canal cunha. Desligar é rollback deliberado — e
    # devolve a um único segredo de ambiente o poder sobre todos os clientes
    # da organização. Mesmo espírito de `app_env`: o padrão fecha a porta.
    atendimento_isolado: bool = True

    canal_service_url: str = "http://canal-service:8000"
    canal_service_key: str = ""

    tasks_service_url: str = ""
    tasks_service_key: str = ""

    # Regras de agendamento (padrões do PRD; por-org fica para a etapa de configurações)
    granularidade_min: int = 30
    # RF-14: quanto tempo o primeiro da fila tem para aceitar a oferta.
    # Não é reserva — o slot segue livre na grade durante a janela.
    fila_janela_aceite_min: int = 30
    antecedencia_minima_min: int = 60
    janela_maxima_dias: int = 60

    @property
    def dev_mode(self) -> bool:
        return self.app_env != "prod"


@lru_cache
def settings() -> Settings:
    return Settings()
