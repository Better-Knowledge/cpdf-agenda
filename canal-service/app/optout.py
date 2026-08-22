"""Opt-out determinístico (RF-10, IA-04): sair do spam não pode depender de
IA acertar. A detecção roda por regra, ANTES de qualquer LLM ver a mensagem.
"""

import unicodedata

PALAVRAS_OPTOUT = {
    "sair",
    "pare",
    "parar",
    "stop",
    "descadastrar",
    "cancelar inscricao",
    "nao quero mais receber",
    "não quero mais receber mensagens",
}

CONFIRMACAO_OPTOUT = (
    "Pronto — você não vai mais receber mensagens automáticas nossas. "
    "Se mudar de ideia, é só pedir para voltar a receber."
)


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split()).strip(".,!? ")


def e_pedido_de_optout(texto: str) -> bool:
    normalizado = _normalizar(texto)
    return normalizado in {_normalizar(p) for p in PALAVRAS_OPTOUT}
