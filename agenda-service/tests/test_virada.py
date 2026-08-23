"""A virada (etapa 6): o que deixou de valer, e o que foi feito para não doer.

Duas portas se fecham aqui. A primeira é `AGENT_API_KEYS` — chave estática no
ambiente, sem escopo próprio e sem revogação a não ser por redeploy: exatamente
o que o RF-18 existe para substituir. A segunda é `X-Service-Key`, testada em
`test_proximo.py`.

Fechar por si só seria fácil; o trabalho é fechar **sem deslogar ninguém** e
sem tirar da tela de Integrações quem já a usava.
"""

import json
import uuid

import pytest

from app.auth import ESCOPO_CREDENCIAIS, limpar_cache

from .conftest import integracao

pytestmark = integracao


@pytest.fixture(autouse=True)
def _cache_limpo():
    limpar_cache()
    yield
    limpar_cache()


def chave_antiga() -> str:
    """Uma por teste: o banco é da sessão inteira, e importar duas vezes o
    mesmo valor é justamente o caso do teste de idempotência."""
    return f"demo-alunos-{uuid.uuid4().hex[:12]}"


def test_a_flag_de_isolamento_vem_ligada():
    """Mesmo espírito de `app_env`: o padrão fecha a porta. Um deploy que
    esqueça a variável não pode devolver a organização inteira a um segredo
    de ambiente."""
    from app.config import Settings

    assert Settings().atendimento_isolado is True


def test_agent_api_keys_nao_autentica_mais(client, catalogo, monkeypatch):
    """A chave está no ambiente e não abre nada — porque não está no banco."""
    chave = chave_antiga()
    monkeypatch.setenv("AGENT_API_KEYS", json.dumps({chave: str(uuid.uuid4())}))
    resposta = client.get("/services", headers={"X-Agent-Key": chave})
    assert resposta.status_code == 401
    assert resposta.json()["code"] == "NAO_AUTENTICADO"
    # a mensagem diz o que fazer, não só que deu errado
    assert "importar-env" in resposta.json()["message"]


def test_o_setting_sumiu_de_vez(monkeypatch):
    """Não basta ignorar o valor: enquanto o campo existir em `Settings`,
    alguém volta a consultá-lo achando que é caminho suportado."""
    from app.config import Settings

    assert "agent_api_keys" not in Settings.model_fields


def test_importar_env_migra_sem_deslogar_ninguem(client, banco_migrado, org_id, monkeypatch):
    """O valor da chave é preservado: a que está no localStorage do navegador
    do aluno continua funcionando depois da migração. Se a migração emitisse
    uma chave nova, a virada viraria 'todo mundo perdeu o acesso'."""
    from app.admin_cli import importar_env

    chave = chave_antiga()
    monkeypatch.setenv("AGENT_API_KEYS", json.dumps({chave: str(org_id)}))
    assert importar_env() == 1
    limpar_cache()

    # Mesmo header, mesmo valor, mesma sessão do navegador — agora resolvido
    # em `agent_credentials`, com escopo próprio e revogável.
    assert client.get("/services", headers={"X-Agent-Key": chave}).status_code == 200
    assert client.get("/credenciais/eu", headers={"X-Agent-Key": chave}).json()["ator"] == "agente"


def test_a_chave_migrada_ainda_abre_a_tela_de_integracoes(client, banco_migrado, org_id, monkeypatch):
    """A chave migrada tinha autoridade total, inclusive sobre credenciais. Uma
    migração que silenciosamente tirasse esse poder deixaria a T-11 dando 403
    sem explicar por quê — o pior tipo de regressão, a que parece bug."""
    from app.admin_cli import importar_env

    chave = chave_antiga()
    monkeypatch.setenv("AGENT_API_KEYS", json.dumps({chave: str(org_id)}))
    importar_env()
    limpar_cache()

    eu = client.get("/credenciais/eu", headers={"X-Agent-Key": chave}).json()
    assert ESCOPO_CREDENCIAIS in eu["escopos"]
    assert client.get("/credenciais", headers={"X-Agent-Key": chave}).status_code == 200


def test_importar_env_e_idempotente(client, banco_migrado, org_id, monkeypatch):
    """Rodar de novo depois de um deploy repetido não duplica a credencial —
    a chave é a mesma, e o hash dela também."""
    from app.admin_cli import importar_env

    chave = chave_antiga()
    monkeypatch.setenv("AGENT_API_KEYS", json.dumps({chave: str(org_id)}))
    assert importar_env() == 1
    assert importar_env() == 0
    limpar_cache()
    assert len(client.get("/credenciais", headers={"X-Agent-Key": chave}).json()) == 1


def test_importar_env_le_o_ambiente_e_nao_o_settings(monkeypatch):
    """A ferramenta de migração precisa ler AGENT_API_KEYS mesmo depois de o
    caminho de autenticação parar de honrá-la — senão quem atualiza o código
    perde a chave antes de ter como migrá-la."""
    from app.admin_cli import _chaves_do_ambiente

    monkeypatch.delenv("AGENT_API_KEYS", raising=False)
    assert _chaves_do_ambiente() == {}
    monkeypatch.setenv("AGENT_API_KEYS", "{}")
    assert _chaves_do_ambiente() == {}
    monkeypatch.setenv("AGENT_API_KEYS", json.dumps({"a": "b"}))
    assert _chaves_do_ambiente() == {"a": "b"}
