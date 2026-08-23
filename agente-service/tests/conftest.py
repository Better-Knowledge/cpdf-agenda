import os

os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("AGENTE_SERVICE_KEY", "chave-do-agente-teste")
os.environ.setdefault("ANTHROPIC_API_KEY", "")  # testes não chamam LLM de verdade

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def sem_memoria_entre_testes():
    """O contador do fallback em duas etapas é global — zera entre testes."""
    from app.fluxo import _TENTATIVAS

    _TENTATIVAS.clear()
    yield
    _TENTATIVAS.clear()


@pytest.fixture()
def agenda_falsa(monkeypatch):
    """Substitui as chamadas HTTP por respostas controladas e registra o que
    o agente tentou fazer — é assim que verificamos que ele não inventou
    caminho fora da API."""
    from app import clientes

    class Falsa:
        def __init__(self):
            self.compromisso: dict | None = None
            self.slots: list[dict] = []
            self.fila: list[dict] = []
            self.aceite: tuple[int, dict] | None = None
            self.chamadas: list[tuple[str, str]] = []
            self.sessoes: list = []
            self.respostas: list[str] = []

        def agenda(self, metodo, rota, sessao, corpo=None):
            # Guarda a sessão junto: os testes de isolamento verificam que o
            # agente chamou a agenda COM o token, e não com a chave do serviço.
            self.chamadas.append((metodo, rota))
            self.sessoes.append(sessao)
            if rota.startswith("/appointments/proximo"):
                return (200, self.compromisso) if self.compromisso else (404, {"code": "NAO_ENCONTRADO"})
            if rota.startswith("/slots"):
                return 200, self.slots
            if rota.endswith("/confirm"):
                return 200, {**(self.compromisso or {}), "status": "confirmado"}
            if rota == "/waitlist":
                return 200, self.fila
            if rota.endswith("/aceitar"):
                return self.aceite or (200, {**(self.compromisso or {}), "id": "novo"})
            return 200, {}

        def responder(self, sessao, texto):
            self.respostas.append(texto)

    falsa = Falsa()
    monkeypatch.setattr(clientes, "agenda", falsa.agenda)
    monkeypatch.setattr(clientes, "responder", falsa.responder)
    import app.fluxo as fluxo

    monkeypatch.setattr(fluxo.clientes, "agenda", falsa.agenda)
    monkeypatch.setattr(fluxo.clientes, "responder", falsa.responder)
    return falsa


OFERTA_NA_FILA = {
    "id": "f11a0000-0000-4000-8000-000000000001",
    "cliente_telefone": "+5511999998888",
    "status": "ofertado",
    "slot_ofertado": "2026-08-27T15:30:00-03:00",
}

COMPROMISSO = {
    "id": "0b6ff65e-4f2a-4c8d-9e1b-3a5c7d9f0e2a",
    "service_id": "b3f0a1d4-2c5e-4f6a-8b7c-9d0e1f2a3b4c",
    "resource_id": "6f1e0c2a-8f6e-4b9e-9d3a-0d5b2a7c9c02",
    "label_humano": "quinta, 27 de agosto, 15h30",
    "status": "agendado",
}
