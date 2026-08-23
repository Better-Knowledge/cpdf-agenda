"""O que o agente faz com cada intenção (IA-04).

Gradiente de risco do programa, aplicado literalmente:
- **reversível** (confirmar presença) → o agente age sozinho;
- **negócio** (remarcar) → propõe horários e espera a escolha;
- **irreversível** (cancelar) → NUNCA pelo agente: vai para o humano com a
  conversa marcada, porque cancelar libera o slot para outra pessoa.

Fallback em duas etapas: intenção incerta → o agente pergunta; se a próxima
mensagem também não for reconhecida, a conversa vai para o humano.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from uuid import UUID

from . import clientes
from .intencao import LIMITE_CONFIANCA, Intencao, classificar

log = logging.getLogger("agente.fluxo")

# Memória curta: quantas vezes seguidas não entendemos este telefone.
# Em processo, de propósito — a fila de humanos é a persistência que importa.
_TENTATIVAS: dict[tuple[str, str], int] = {}


@dataclass
class Resultado:
    intencao: str
    confianca: float
    acao: str  # confirmado | proposto | aguardando_humano | esclarecimento | ignorado
    resposta: str | None = None
    detalhes: dict = field(default_factory=dict)


def _chave(org_id: UUID, telefone: str) -> tuple[str, str]:
    return (str(org_id), telefone)


def _para_humano(org_id: UUID, telefone: str, texto: str, motivo: str) -> Resultado:
    """Fila 'aguardando humano': hoje é log + aviso ao cliente; a tarefa no
    Gestor de Tarefas entra na etapa 7 (RF-07), com o mesmo gatilho."""
    log.warning("aguardando humano | org=%s tel=%s motivo=%s texto=%r", org_id, telefone, motivo, texto)
    resposta = (
        "Vou pedir para alguém da equipe falar com você — em breve te respondem por aqui."
    )
    clientes.responder(org_id, telefone, resposta)
    _TENTATIVAS.pop(_chave(org_id, telefone), None)
    return Resultado(
        intencao="—", confianca=0.0, acao="aguardando_humano", resposta=resposta,
        detalhes={"motivo": motivo},
    )


def _proximo_compromisso(org_id: UUID, telefone: str) -> dict | None:
    status, corpo = clientes.agenda(
        "GET", f"/appointments/proximo?telefone={quote(telefone)}", org_id
    )
    return corpo if status == 200 else None


def _confirmar(org_id: UUID, telefone: str, compromisso: dict) -> Resultado:
    status, corpo = clientes.agenda(
        "POST", f"/appointments/{compromisso['id']}/confirm", org_id
    )
    if status >= 400 and corpo.get("code") != "STATUS_INCOMPATIVEL":
        return _para_humano(org_id, telefone, "", f"confirmação falhou: {corpo.get('code')}")
    resposta = f"Presença confirmada — {compromisso['label_humano']}. Até lá!"
    clientes.responder(org_id, telefone, resposta)
    return Resultado(
        intencao="confirmar", confianca=1.0, acao="confirmado", resposta=resposta,
        detalhes={"appointment_id": compromisso["id"]},
    )


def _propor_remarcacao(org_id: UUID, telefone: str, compromisso: dict) -> Resultado:
    """Remarcar é decisão de negócio: o agente PROPÕE, o cliente escolhe.

    Quem move o compromisso é o reagendamento atômico da agenda (RF-06) —
    o agente não inventa caminho paralelo.
    """
    de = datetime.now(UTC) + timedelta(hours=1)
    ate = de + timedelta(days=14)
    status, slots = clientes.agenda(
        "GET",
        f"/slots?service_id={compromisso['service_id']}&resource_id={compromisso['resource_id']}"
        # o offset traz '+', que numa query string vira espaço — precisa escapar
        f"&from={quote(de.isoformat())}&to={quote(ate.isoformat())}&limit=3",
        org_id,
    )
    if status >= 400 or not slots:
        return _para_humano(org_id, telefone, "", "sem horários livres para propor")
    opcoes = "\n".join(f"• {s['label_humano']}" for s in slots)
    resposta = (
        f"Seu horário hoje é {compromisso['label_humano']}.\n"
        f"Posso trocar para um destes:\n{opcoes}\n\nQual prefere?"
    )
    clientes.responder(org_id, telefone, resposta)
    return Resultado(
        intencao="remarcar", confianca=1.0, acao="proposto", resposta=resposta,
        detalhes={"alternativas": [s["inicio"] for s in slots]},
    )


def tratar(org_id: UUID, telefone: str, texto: str) -> Resultado:
    compromisso = _proximo_compromisso(org_id, telefone)
    contexto = (
        f"Tem {compromisso['label_humano']} marcado ({compromisso['status']})."
        if compromisso
        else "Não tem compromisso futuro marcado."
    )
    intencao: Intencao = classificar(texto, contexto)
    log.info(
        "intenção=%s confiança=%.2f por=%s tel=%s", intencao.nome, intencao.confianca, intencao.por, telefone
    )

    # Fallback em duas etapas: incerto → pergunta; incerto de novo → humano.
    if intencao.confianca < LIMITE_CONFIANCA:
        chave = _chave(org_id, telefone)
        _TENTATIVAS[chave] = _TENTATIVAS.get(chave, 0) + 1
        if _TENTATIVAS[chave] >= 2:
            return _para_humano(org_id, telefone, texto, "segunda falha de interpretação")
        resposta = (
            "Não tenho certeza se entendi. Você quer *confirmar*, *remarcar* ou "
            "*cancelar* o seu horário?"
        )
        clientes.responder(org_id, telefone, resposta)
        return Resultado(
            intencao=intencao.nome, confianca=intencao.confianca, acao="esclarecimento",
            resposta=resposta,
        )

    _TENTATIVAS.pop(_chave(org_id, telefone), None)

    if intencao.nome in ("confirmar", "cancelar", "remarcar") and compromisso is None:
        resposta = (
            "Não encontrei um horário futuro no seu nome. Quer marcar um agora? "
            "Me diga o dia e o período que prefere."
        )
        clientes.responder(org_id, telefone, resposta)
        return Resultado(
            intencao=intencao.nome, confianca=intencao.confianca, acao="esclarecimento",
            resposta=resposta,
        )

    if intencao.nome == "confirmar":
        return _confirmar(org_id, telefone, compromisso)

    if intencao.nome == "remarcar":
        return _propor_remarcacao(org_id, telefone, compromisso)

    if intencao.nome == "cancelar":
        # Irreversível: o slot volta para a grade e outra pessoa pode pegar.
        # A classificação de intenção NÃO substitui a confirmação humana (RF-06).
        return _para_humano(org_id, telefone, texto, "cancelamento pedido pelo cliente")

    if intencao.nome in ("duvida", "aceitar_oferta"):
        return _para_humano(org_id, telefone, texto, f"intenção '{intencao.nome}' precisa de humano")

    # fora_de_contexto: não responde nada — evita conversa paralela com o bot.
    log.info("fora de contexto, sem resposta | tel=%s", telefone)
    return Resultado(intencao=intencao.nome, confianca=intencao.confianca, acao="ignorado")
