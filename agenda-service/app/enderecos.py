# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Fernando Melo Faraco <fernando.faraco@better-knowledge.com.br>

"""Endereço do cliente no canal — uma forma canônica só.

O invariante do programa diz que `cliente_telefone` significa "endereço neste
canal": E.164 no WhatsApp, `tg:<chat_id>` no Telegram. O que ele não dizia até
aqui é que a **forma** importa. A partir do isolamento por titular (RF-19), a
comparação `cliente_telefone == titular` decide se o cliente enxerga o próprio
horário — e `+55 11 99876-5432` não é igual a `+5511998765432`.

Um cliente que perde acesso ao próprio compromisso por causa de um espaço é
pior do que o vazamento que o isolamento veio fechar: falha silenciosa, e o
agente responde "não encontrei nada no seu nome" com toda a confiança.

Por isso a normalização é ponto único, aplicada na escrita, no backfill
(migration 0004) e na cunhagem do token de sessão.
"""

import re

PREFIXO_TELEGRAM = "tg:"
_NAO_DIGITO = re.compile(r"\D")
# `tg:`, `mail:`, o que vier depois — um esquema explícito não é telefone.
_ESQUEMA = re.compile(r"^([a-z][a-z0-9+.-]*):(.*)$", re.IGNORECASE)


def normalizar(endereco: str | None) -> str:
    """Forma canônica do endereço. Idempotente: normalizar duas vezes não muda.

    - com esquema (`tg:123`, `TG: 123`) → esquema em minúsculas, resto sem espaços
    - sem esquema → E.164: só dígitos, com `+` na frente
    - sem dígito nenhum e sem esquema → devolve como veio, apenas aparado.
      Não é papel daqui recusar: quem valida entrada é o schema Pydantic, e
      engolir um endereço estranho em silêncio seria pior do que carregá-lo.
    """
    bruto = (endereco or "").strip()
    if not bruto:
        return ""

    if m := _ESQUEMA.match(bruto):
        esquema, resto = m.group(1).lower(), m.group(2).strip()
        return f"{esquema}:{resto}"

    digitos = _NAO_DIGITO.sub("", bruto)
    return f"+{digitos}" if digitos else bruto


def e_telegram(endereco: str) -> bool:
    return normalizar(endereco).startswith(PREFIXO_TELEGRAM)


def mesmo(a: str | None, b: str | None) -> bool:
    """Comparação de endereços — nunca compare as strings cruas."""
    return bool(a) and bool(b) and normalizar(a) == normalizar(b)
