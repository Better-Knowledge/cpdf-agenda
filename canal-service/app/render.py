"""Renderização de templates com {{variaveis}}.

Variável sem valor NÃO sai como buraco no texto: mensagem ativa com template
quebrado é pior que mensagem nenhuma (IA-02: sem template aprovado → não sai).
"""

import re

from .errors import ApiError

PADRAO_VARIAVEL = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def variaveis_do_template(corpo: str) -> set[str]:
    return set(PADRAO_VARIAVEL.findall(corpo))


def renderizar(corpo: str, variaveis: dict[str, str]) -> str:
    faltando = variaveis_do_template(corpo) - set(variaveis)
    if faltando:
        raise ApiError(
            code="VARIAVEL_FALTANDO",
            message=f"O template exige variáveis não informadas: {', '.join(sorted(faltando))}.",
            hint="Envie todas as variáveis do template no campo `variaveis`.",
        )
    return PADRAO_VARIAVEL.sub(lambda m: str(variaveis[m.group(1)]), corpo)
