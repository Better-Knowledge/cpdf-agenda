"""IA-04 — classificação da resposta do cliente.

Duas camadas, nesta ordem:

1. **Regra determinística** para o que é inequívoco ("confirmo", "não vou
   poder"). Barato, instantâneo, testável — e não depende de nuvem.
2. **LLM** só para o que sobra, com saída fechada em JSON.

O que a classificação NÃO faz: pular regra de negócio. Ela devolve uma
intenção; quem age é o `acoes.py`, chamando a API da agenda — cancelamento
continua exigindo confirmação humana (RF-06).

Baixa confiança nunca vira ação: vira pedido de esclarecimento e, na segunda
falha, a conversa vai para o humano.
"""

import json
import logging
import re
import unicodedata
from dataclasses import dataclass

from .config import settings

log = logging.getLogger("agente.intencao")

INTENCOES = (
    "confirmar",
    "cancelar",
    "remarcar",
    "aceitar_oferta",
    "duvida",
    "fora_de_contexto",
)


@dataclass(frozen=True)
class Intencao:
    nome: str
    confianca: float  # 0..1 — abaixo de LIMITE_CONFIANCA não vira ação
    por: str  # "regra" ou "llm"
    justificativa: str = ""


LIMITE_CONFIANCA = 0.7


def _normalizar(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sem_acento).strip(" .!?,")


# Frases inteiras, não fragmentos: "confirmo" bate; "não posso confirmar" não.
_REGRAS: tuple[tuple[str, str], ...] = (
    (r"^(sim|isso|ok|okay|blz|beleza|confirmo|confirmado|confirmar)$", "confirmar"),
    (r"^(sim,? )?(vou|estarei|estarei la|to indo|tudo certo|pode marcar|confirmo).{0,20}$", "confirmar"),
    (r"^(nao|nao vou|nao posso|nao consigo|nao da|nao vai dar)( poder)?( ir| comparecer)?$", "cancelar"),
    (r"^(quero |preciso )?cancelar.{0,20}$", "cancelar"),
    (r"^(quero |preciso |podemos |da pra )?(remarcar|reagendar|mudar|adiar|trocar).{0,30}$", "remarcar"),
    (r"^(quero|aceito|pode ser|fico com|pego)( esse| este| o)? horario.{0,20}$", "aceitar_oferta"),
)


def por_regra(texto: str) -> Intencao | None:
    normalizado = _normalizar(texto)
    for padrao, intencao in _REGRAS:
        if re.match(padrao, normalizado):
            return Intencao(nome=intencao, confianca=1.0, por="regra", justificativa=padrao)
    return None


PROMPT = """\
Você classifica a resposta de um cliente no WhatsApp de uma agenda de atendimentos.

Contexto do cliente (pode estar vazio):
{contexto}

Mensagem do cliente:
"{texto}"

Classifique em UMA destas intenções:
- confirmar: confirma presença no compromisso
- cancelar: não vai comparecer e quer desmarcar
- remarcar: quer outro dia/horário
- aceitar_oferta: aceita um horário que foi oferecido a ele
- duvida: pergunta sobre preço, endereço, serviço, horário, "quem fala?"
- fora_de_contexto: não tem relação com a agenda

Responda SÓ com JSON: {{"intencao": "<uma das acima>", "confianca": <0.0 a 1.0>, \
"justificativa": "<motivo em até 12 palavras>"}}

Seja honesto na confiança: mensagem ambígua ou que mistura intenções recebe \
confiança abaixo de 0.7 — é melhor perguntar do que agir errado."""


def por_llm(texto: str, contexto: str = "") -> Intencao | None:
    cfg = settings()
    if not cfg.anthropic_api_key:
        return None
    try:
        import anthropic

        cliente = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
        resposta = cliente.messages.create(
            model=cfg.modelo,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": PROMPT.format(texto=texto, contexto=contexto or "(sem contexto)"),
                }
            ],
        )
        bruto = resposta.content[0].text.strip()
        dados = json.loads(bruto[bruto.index("{") : bruto.rindex("}") + 1])
    except Exception:
        log.exception("classificação por LLM falhou — vai para o humano")
        return None
    nome = dados.get("intencao")
    if nome not in INTENCOES:
        return None
    return Intencao(
        nome=nome,
        confianca=float(dados.get("confianca", 0)),
        por="llm",
        justificativa=str(dados.get("justificativa", ""))[:120],
    )


def classificar(texto: str, contexto: str = "") -> Intencao:
    """Regra primeiro; LLM só no que sobra. Nada reconhecido → duvida com
    confiança 0, que o fluxo trata como 'pergunte ao cliente'."""
    if regra := por_regra(texto):
        return regra
    if llm := por_llm(texto, contexto):
        return llm
    return Intencao(nome="duvida", confianca=0.0, por="regra", justificativa="não reconhecida")
