"""RF-12 — Google Calendar: push assíncrono e busy-read degradável.

O Google nunca é chamado de verdade aqui. O que estes testes protegem são as
promessas do RF-12 que valem justamente quando o Google **não** responde:
agendar continua funcionando, o push tenta de novo, e o motor de slots volta
ao cálculo local em vez de derrubar a consulta.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app import crypto, google_sync
from app import google_calendar as gcal
from app.errors import ApiError

from .conftest import integracao

# ── OAuth: o state é a única coisa que atravessa o navegador ─────────────────


def test_o_state_do_oauth_e_assinado_e_expira():
    from app import estado_oauth

    org, recurso = uuid.uuid4(), uuid.uuid4()
    state = estado_oauth.emitir(org, recurso)
    assert estado_oauth.validar(state) == (org, recurso)

    corpo, assinatura = state.split(".")
    adulterado = corpo + "." + ("0" * len(assinatura))
    with pytest.raises(ApiError) as e:
        estado_oauth.validar(adulterado)
    assert e.value.code == "OAUTH_ESTADO_INVALIDO"


def test_confirmation_token_nao_serve_como_state(monkeypatch):
    """Domínios de HMAC separados: os dois usam o mesmo segredo, e sem o
    prefixo de domínio um token de cancelamento viraria autorização para
    ligar uma conta do Google a um recurso qualquer."""
    from app import confirmacao, estado_oauth

    token = confirmacao.gerar_token("cancel", uuid.uuid4())
    with pytest.raises(ApiError):
        estado_oauth.validar(token)


def test_a_renovacao_preserva_o_refresh_token():
    """O Google não repete o refresh_token na renovação. Perdê-lo é perder a
    conexão — o prestador teria de reconectar na mão em uma hora."""
    creds = gcal.Credenciais.de_resposta(
        {"access_token": "novo", "expires_in": 3600}, refresh_token="o-antigo"
    )
    assert creds.refresh_token == "o-antigo"
    assert not creds.vencido


def test_token_perto_do_vencimento_ja_conta_como_vencido():
    creds = gcal.Credenciais(
        access_token="a", refresh_token="r", expira_em=datetime.now(UTC) + timedelta(minutes=2)
    )
    assert creds.vencido  # margem de 5 min: renova antes de falhar


# ── Push e busy-read (com banco) ─────────────────────────────────────────────


class GoogleFake:
    """Substitui a API do Google: registra chamadas e permite simular falha."""

    def __init__(self):
        self.criados: list[dict] = []
        self.atualizados: list[str] = []
        self.removidos: list[str] = []
        self.busy: list[tuple[datetime, datetime]] = []
        self.erro: Exception | None = None
        self.proximo_id = 0

    def criar_evento(self, token, calendar_id, evento):
        if self.erro:
            raise self.erro
        self.proximo_id += 1
        self.criados.append(evento)
        return f"evento-{self.proximo_id}"

    def atualizar_evento(self, token, calendar_id, event_id, evento):
        if self.erro:
            raise self.erro
        self.atualizados.append(event_id)

    def remover_evento(self, token, calendar_id, event_id):
        if self.erro:
            raise self.erro
        self.removidos.append(event_id)

    def livre_ocupado(self, token, calendar_id, de, ate):
        if self.erro:
            raise self.erro
        return self.busy


@pytest.fixture()
def google(monkeypatch):
    from app.config import settings

    fake = GoogleFake()
    monkeypatch.setattr(settings(), "google_client_id", "cliente-de-teste")
    monkeypatch.setattr(settings(), "google_client_secret", "segredo-de-teste")
    for nome in ("criar_evento", "atualizar_evento", "remover_evento", "livre_ocupado"):
        monkeypatch.setattr(gcal, nome, getattr(fake, nome))
    google_sync.limpar_cache()
    yield fake
    google_sync.limpar_cache()


@pytest.fixture()
def conectado(client, catalogo, org_id, google):
    """Recurso do catálogo com Google conectado (tokens cifrados, válidos)."""
    from app.models import GoogleCalendarLink
    from app.sessao import SessionLocal, sessao_org

    creds = gcal.Credenciais(
        access_token="token-de-acesso",
        refresh_token="token-de-renovacao",
        expira_em=datetime.now(UTC) + timedelta(hours=1),
    )
    with SessionLocal() as db:
        sessao_org(db, org_id)
        db.add(
            GoogleCalendarLink(
                org_id=org_id,
                resource_id=uuid.UUID(catalogo["recurso"]["id"]),
                calendar_id="primary",
                credenciais=crypto.cifrar(creds.como_dict()),
            )
        )
        db.commit()
    return catalogo


def _agendar(client, catalogo, hora: int = 10, dia: int = 5):
    inicio = (datetime.now(UTC) + timedelta(days=dia)).replace(
        hour=hora, minute=0, second=0, microsecond=0
    )
    resposta = client.post(
        "/appointments",
        json={
            "service_id": catalogo["servico"]["id"],
            "resource_id": catalogo["recurso"]["id"],
            "inicio": inicio.isoformat(),
            "cliente_nome": "Bruno Lima",
            "cliente_telefone": "+5511966665555",
        },
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


@integracao
def test_agendar_empurra_o_evento_para_o_google(client, conectado, google):
    ap = _agendar(client, conectado)
    assert google.criados == []  # o push é assíncrono: agendar não espera o Google

    google_sync.processar_pendentes()
    (evento,) = google.criados
    assert "Bruno Lima" in evento["summary"]
    assert "gerencie por lá" in evento["description"]  # one-way, avisado no evento

    from app.sessao import SessionLocal, sessao_org

    with SessionLocal() as db:
        sessao_org(db, uuid.UUID(ap["id"]) and _org(client))
        pass


def _org(client) -> uuid.UUID:
    return uuid.UUID(client.headers["X-Org-Id"])


@integracao
def test_cancelar_remove_o_evento_do_google(client, conectado, google):
    ap = _agendar(client, conectado, hora=11)
    google_sync.processar_pendentes()
    assert len(google.criados) == 1

    client.post(f"/appointments/{ap['id']}/cancel", json={"motivo": "cliente pediu"})
    google_sync.processar_pendentes()
    assert google.removidos == ["evento-1"]


@integracao
def test_reagendar_atualiza_o_mesmo_evento(client, conectado, google):
    ap = _agendar(client, conectado, hora=12)
    google_sync.processar_pendentes()

    novo = (datetime.now(UTC) + timedelta(days=6)).replace(
        hour=14, minute=0, second=0, microsecond=0
    )
    resposta = client.post(
        f"/appointments/{ap['id']}/reschedule", json={"novo_inicio": novo.isoformat()}
    )
    assert resposta.status_code == 200, resposta.text
    google_sync.processar_pendentes()
    assert google.atualizados == ["evento-1"]
    assert len(google.criados) == 1  # não duplica no calendário


@integracao
def test_google_fora_do_ar_nao_impede_agendar_e_a_entrega_espera(client, conectado, google):
    """O critério do RF-12 em uma frase: falha na API do Google não bloqueia
    o agendamento."""
    google.erro = gcal.GoogleIndisponivel("timeout")
    ap = _agendar(client, conectado, hora=13)
    assert ap["id"]

    assert google_sync.processar_pendentes() == 0
    from app.models import DomainEvent, EventDelivery
    from app.sessao import SessionLocal, sessao_worker

    with SessionLocal() as db:
        sessao_worker(db)
        # `event_deliveries` não tem org_id (é contabilidade de entrega, não
        # dado de negócio): a ligação com esta organização é pelo evento.
        (entrega,) = (
            db.query(EventDelivery)
            .join(DomainEvent, DomainEvent.id == EventDelivery.event_id)
            .filter(DomainEvent.org_id == _org(client))
            .all()
        )
        assert entrega.attempts == 1
        assert entrega.processed_at is None  # continua pendente, para tentar de novo
        assert "timeout" in entrega.last_error

    google.erro = None
    # A próxima tentativa é ancorada no evento (1, 2, 4… min). Envelhecer o
    # evento é o equivalente a esperar o backoff.
    with SessionLocal() as db:
        sessao_worker(db)
        db.query(DomainEvent).filter(DomainEvent.org_id == _org(client)).update(
            {"occurred_at": datetime.now(UTC) - timedelta(minutes=10)}
        )
        db.commit()
    assert google_sync.processar_pendentes() == 1
    assert len(google.criados) == 1


@integracao
def test_recusa_definitiva_desconecta_em_vez_de_insistir(client, conectado, google, org_id):
    """Token revogado do lado do Google não melhora com repetição: a conexão
    é marcada inativa e a tela passa a pedir reconexão."""
    google.erro = gcal.GoogleRecusou("401: invalid_grant")
    _agendar(client, conectado, hora=15)
    google_sync.processar_pendentes()

    conexoes = client.get("/integracoes/google").json()
    assert conexoes[0]["precisa_reconectar"] is True
    assert conexoes[0]["ativo"] is False


@integracao
def test_busy_do_google_bloqueia_o_slot(client, conectado, google):
    """Reunião marcada direto no Google não pode ser oferecida como livre."""
    dia = _dia_util(7)
    livres = _slots(client, conectado, dia)
    assert any(s.startswith(dia.isoformat()[:13]) for s in livres)

    google.busy = [(dia, dia + timedelta(hours=1))]
    google_sync.limpar_cache()
    depois = _slots(client, conectado, dia)
    assert not any(s.startswith(dia.isoformat()[:13]) for s in depois)
    assert depois  # os outros horários do dia continuam livres


@integracao
def test_busy_indisponivel_degrada_para_o_calculo_local(client, conectado, google):
    dia = _dia_util(8)
    google.erro = gcal.GoogleIndisponivel("connect timeout")
    google_sync.limpar_cache()
    livres = _slots(client, conectado, dia)
    assert livres, "Google fora do ar não pode zerar a agenda"


def _dia_util(daqui_a: int) -> datetime:
    """10h em hora de parede de São Paulo — a grade do catálogo é 9h–18h local,
    e montar o horário em UTC cairia fora dela."""
    from app.tempo import TZ

    dia = (datetime.now(TZ) + timedelta(days=daqui_a)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    while dia.weekday() > 4:  # a grade do catálogo é de segunda a sexta
        dia += timedelta(days=1)
    return dia


def _slots(client, catalogo, dia) -> list[str]:
    resposta = client.get(
        "/slots",
        params={
            "service_id": catalogo["servico"]["id"],
            "from": dia.replace(hour=8).isoformat(),
            "to": dia.replace(hour=18).isoformat(),
        },
    )
    assert resposta.status_code == 200, resposta.text
    return [s["inicio"] for s in resposta.json()]


# ── Rotas ────────────────────────────────────────────────────────────────────


@integracao
def test_conectar_devolve_a_url_de_consentimento(client, catalogo, google):
    resposta = client.post(
        "/integracoes/google/conectar", json={"resource_id": catalogo["recurso"]["id"]}
    )
    assert resposta.status_code == 200, resposta.text
    url = resposta.json()["url"]
    assert url.startswith("https://accounts.google.com/")
    assert "access_type=offline" in url  # sem isso não vem refresh_token
    assert "calendar.events" in url
    assert "state=" in url


@integracao
def test_sem_app_oauth_a_rota_explica_o_caminho_sem_oauth(client, catalogo):
    resposta = client.post(
        "/integracoes/google/conectar", json={"resource_id": catalogo["recurso"]["id"]}
    )
    assert resposta.status_code == 409
    corpo = resposta.json()
    assert corpo["code"] == "GOOGLE_NAO_CONFIGURADO"
    assert ".ics" in corpo["hint"]  # o fallback sem OAuth está no próprio erro


@integracao
def test_callback_com_state_forjado_e_recusado(client):
    resposta = client.get(
        "/integracoes/google/callback",
        params={"code": "qualquer", "state": "inventado.aaaa"},
        follow_redirects=False,
    )
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "OAUTH_ESTADO_INVALIDO"


@integracao
def test_desconectar_apaga_o_segredo_e_e_idempotente(client, conectado, google, catalogo):
    primeira = client.delete(f"/integracoes/google/{catalogo['recurso']['id']}").json()
    assert primeira["desconectado"] is True

    from app.models import GoogleCalendarLink
    from app.sessao import SessionLocal, sessao_org

    with SessionLocal() as db:
        sessao_org(db, _org(client))
        (link,) = db.query(GoogleCalendarLink).all()
        assert link.credenciais == {}  # o segredo sai do banco
        assert link.revogado_em is not None

    segunda = client.delete(f"/integracoes/google/{catalogo['recurso']['id']}").json()
    assert segunda["desconectado"] is False


@integracao
def test_a_listagem_nunca_devolve_token(client, conectado, google):
    import json

    corpo = json.dumps(client.get("/integracoes/google").json())
    assert "token-de-acesso" not in corpo
    assert "token-de-renovacao" not in corpo
    assert "credenciais" not in corpo
