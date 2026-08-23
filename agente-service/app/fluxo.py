# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

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

from . import clientes
from .clientes import Sessao
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


def _chave(sessao: Sessao) -> tuple[str, str]:
    return (str(sessao.org_id), sessao.telefone)


def _para_humano(sessao: Sessao, texto: str, motivo: str) -> Resultado:
    """Fila 'aguardando humano': hoje é log + aviso ao cliente; a tarefa no
    Gestor de Tarefas entra na etapa 7 (RF-07), com o mesmo gatilho."""
    log.warning(
        "aguardando humano | org=%s tel=%s motivo=%s texto=%r",
        sessao.org_id, sessao.telefone, motivo, texto,
    )
    resposta = (
        "Vou pedir para alguém da equipe falar com você — em breve te respondem por aqui."
    )
    clientes.responder(sessao, resposta)
    _TENTATIVAS.pop(_chave(sessao), None)
    return Resultado(
        intencao="—", confianca=0.0, acao="aguardando_humano", resposta=resposta,
        detalhes={"motivo": motivo},
    )


def _proximo_compromisso(sessao: Sessao) -> dict | None:
    # Numa sessão isolada a agenda ignora o parâmetro e responde pelo titular
    # do token. Ele continua sendo enviado para o modo legado — e para que o
    # log da agenda mostre por quem o agente achava que estava perguntando.
    status, corpo = clientes.agenda(
        "GET", f"/appointments/proximo?telefone={quote(sessao.telefone)}", sessao
    )
    return corpo if status == 200 else None


def _confirmar(sessao: Sessao, compromisso: dict) -> Resultado:
    status, corpo = clientes.agenda(
        "POST", f"/appointments/{compromisso['id']}/confirm", sessao
    )
    if status >= 400 and corpo.get("code") != "STATUS_INCOMPATIVEL":
        return _para_humano(sessao, "", f"confirmação falhou: {corpo.get('code')}")
    resposta = f"Presença confirmada — {compromisso['label_humano']}. Até lá!"
    clientes.responder(sessao, resposta)
    return Resultado(
        intencao="confirmar", confianca=1.0, acao="confirmado", resposta=resposta,
        detalhes={"appointment_id": compromisso["id"]},
    )


def _propor_remarcacao(sessao: Sessao, compromisso: dict) -> Resultado:
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
        sessao,
    )
    if status >= 400 or not slots:
        return _para_humano(sessao, "", "sem horários livres para propor")
    opcoes = "\n".join(f"• {s['label_humano']}" for s in slots)
    resposta = (
        f"Seu horário hoje é {compromisso['label_humano']}.\n"
        f"Posso trocar para um destes:\n{opcoes}\n\nQual prefere?"
    )
    clientes.responder(sessao, resposta)
    return Resultado(
        intencao="remarcar", confianca=1.0, acao="proposto", resposta=resposta,
        detalhes={"alternativas": [s["inicio"] for s in slots]},
    )


def _aceitar_oferta(sessao: Sessao, texto: str) -> Resultado:
    """RF-14: o cliente respondeu 'quero' a uma oferta da fila de espera.

    O aceite pode perder a corrida — não há reserva durante a oferta. Quando
    isso acontece, a agenda devolve as alternativas no próprio erro e o
    cliente recebe as opções em vez de um silêncio.
    """
    status, fila = clientes.agenda("GET", "/waitlist", sessao)
    if status >= 400 or not isinstance(fila, list):
        return _para_humano(sessao, texto, "fila de espera indisponível")

    # Numa sessão isolada a agenda já devolveu SÓ as entradas deste cliente —
    # filtrar por telefone aqui era a defesa que dependia de o agente lembrar
    # dela. No modo legado a lista ainda vem inteira, e o filtro fica.
    ofertas = [
        e
        for e in fila
        if e["status"] == "ofertado"
        and (sessao.isolada or e["cliente_telefone"] == sessao.telefone)
    ]
    if not ofertas:
        resposta = (
            "Não encontrei uma oferta de horário em aberto no seu nome. "
            "Se quiser marcar, me diga o dia e o período que prefere."
        )
        clientes.responder(sessao, resposta)
        return Resultado(
            intencao="aceitar_oferta", confianca=1.0, acao="esclarecimento", resposta=resposta
        )

    entrada = ofertas[0]
    status, corpo = clientes.agenda("POST", f"/waitlist/{entrada['id']}/aceitar", sessao)

    if status < 400:
        resposta = f"Pronto! Seu horário está marcado para {corpo['label_humano']}. Até lá!"
        clientes.responder(sessao, resposta)
        return Resultado(
            intencao="aceitar_oferta", confianca=1.0, acao="agendado", resposta=resposta,
            detalhes={"appointment_id": corpo["id"]},
        )

    if corpo.get("code") == "SLOT_INDISPONIVEL":
        # Perdeu a corrida: o erro já traz as 3 alternativas mais próximas.
        opcoes = [a["label_humano"] for a in corpo.get("alternativas", [])]
        if opcoes:
            resposta = (
                "Que pena — alguém confirmou esse horário antes. "
                f"Tenho estes: {', '.join(opcoes)}. Algum serve?"
            )
            clientes.responder(sessao, resposta)
            return Resultado(
                intencao="aceitar_oferta", confianca=1.0, acao="proposto", resposta=resposta,
                detalhes={"alternativas": opcoes},
            )

    if corpo.get("code") == "OFERTA_EXPIRADA":
        resposta = (
            "O prazo dessa oferta já passou e o horário foi oferecido a outra pessoa. "
            "Quer que eu veja outras opções?"
        )
        clientes.responder(sessao, resposta)
        return Resultado(
            intencao="aceitar_oferta", confianca=1.0, acao="esclarecimento", resposta=resposta
        )

    return _para_humano(sessao, texto, f"aceite da fila falhou: {corpo.get('code')}")


def tratar(sessao: Sessao, texto: str) -> Resultado:
    compromisso = _proximo_compromisso(sessao)
    contexto = (
        f"Tem {compromisso['label_humano']} marcado ({compromisso['status']})."
        if compromisso
        else "Não tem compromisso futuro marcado."
    )
    intencao: Intencao = classificar(texto, contexto)
    log.info(
        "intenção=%s confiança=%.2f por=%s tel=%s",
        intencao.nome, intencao.confianca, intencao.por, sessao.telefone,
    )

    # Fallback em duas etapas: incerto → pergunta; incerto de novo → humano.
    if intencao.confianca < LIMITE_CONFIANCA:
        chave = _chave(sessao)
        _TENTATIVAS[chave] = _TENTATIVAS.get(chave, 0) + 1
        if _TENTATIVAS[chave] >= 2:
            return _para_humano(sessao, texto, "segunda falha de interpretação")
        # A pergunta muda com a situação: oferecer "confirmar ou cancelar" a
        # quem não tem horário nenhum é conversa de robô.
        resposta = (
            "Não tenho certeza se entendi. Você quer confirmar, remarcar ou cancelar "
            "o seu horário?"
            if compromisso
            else (
                "Oi! Ainda não tenho um horário no seu nome. Quer marcar? "
                "Me diga o dia e o período que prefere — alguém da equipe confirma com você."
            )
        )
        clientes.responder(sessao, resposta)
        return Resultado(
            intencao=intencao.nome, confianca=intencao.confianca, acao="esclarecimento",
            resposta=resposta,
        )

    _TENTATIVAS.pop(_chave(sessao), None)

    if intencao.nome in ("confirmar", "cancelar", "remarcar") and compromisso is None:
        resposta = (
            "Não encontrei um horário futuro no seu nome. Quer marcar um agora? "
            "Me diga o dia e o período que prefere."
        )
        clientes.responder(sessao, resposta)
        return Resultado(
            intencao=intencao.nome, confianca=intencao.confianca, acao="esclarecimento",
            resposta=resposta,
        )

    if intencao.nome == "confirmar":
        return _confirmar(sessao, compromisso)

    if intencao.nome == "remarcar":
        return _propor_remarcacao(sessao, compromisso)

    if intencao.nome == "cancelar":
        # Irreversível: o slot volta para a grade e outra pessoa pode pegar.
        # A classificação de intenção NÃO substitui a confirmação humana (RF-06).
        return _para_humano(sessao, texto, "cancelamento pedido pelo cliente")

    if intencao.nome == "aceitar_oferta":
        return _aceitar_oferta(sessao, texto)

    if intencao.nome == "duvida":
        return _para_humano(sessao, texto, "dúvida precisa de humano")

    # fora_de_contexto: não responde nada — evita conversa paralela com o bot.
    log.info("fora de contexto, sem resposta | tel=%s", sessao.telefone)
    return Resultado(intencao=intencao.nome, confianca=intencao.confianca, acao="ignorado")
