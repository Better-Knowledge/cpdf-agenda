# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Quem está chamando — perguntado à agenda, nunca decidido aqui.

O conector valida a credencial **uma vez por sessão** com `GET /credenciais/eu`
por dois motivos práticos:

- **falhar rápido e legível**: sem isso, um token errado só apareceria como um
  401 no meio da primeira tool, e o modelo tentaria de novo com outros
  argumentos, achando que o problema era o payload;
- **deixar rastro**: a chamada passa pela agenda, que é onde a auditoria vive.

O que ele NÃO faz com a resposta: decidir o que pode. Escopo é conferido na
agenda, em toda rota, do mesmo jeito para um `curl` e para uma tool. Guardar a
lista aqui e checá-la antes seria criar uma segunda fonte de verdade — e a que
diverge é sempre a que ninguém olha.
"""

import hashlib
import time

from . import agenda

TTL_S = 60
_CACHE: dict[str, tuple[float, dict]] = {}


def limpar_cache() -> None:
    _CACHE.clear()


async def quem_e(autorizacao: str, *, tool: str) -> dict:
    """`{org_id, nome, papel, ator, escopos, titular}` da credencial do chamador."""
    chave = hashlib.sha256(autorizacao.encode()).hexdigest()
    agora = time.monotonic()
    if (guardado := _CACHE.get(chave)) and guardado[0] > agora:
        return guardado[1]
    identidade = await agenda.chamar("GET", "/credenciais/eu", autorizacao, tool=tool)
    _CACHE[chave] = (agora + TTL_S, identidade)
    return identidade
