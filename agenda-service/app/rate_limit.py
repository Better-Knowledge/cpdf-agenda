"""Limite por IP para as rotas públicas (RF-13).

Janela deslizante em memória do processo. É o suficiente para o que ela
protege — enumeração de agenda e criação em massa por um link público — e é
honesto sobre o que não é: com mais de uma réplica, o limite vale por
réplica, e um reinício zera as contagens. Rate limit distribuído (Redis) e
por credencial (`00` §5.9) são dívida registrada, não escopo desta etapa.
"""

import time
from collections import defaultdict, deque

from .errors import ApiError

_janelas: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def limpar() -> None:
    _janelas.clear()


def exigir(chave: str, ip: str, *, limite: int, janela_segundos: int) -> None:
    agora = time.monotonic()
    marcas = _janelas[(chave, ip)]
    while marcas and marcas[0] <= agora - janela_segundos:
        marcas.popleft()
    if len(marcas) >= limite:
        espera = int(janela_segundos - (agora - marcas[0])) + 1
        raise ApiError(
            code="MUITAS_REQUISICOES",
            message="Muitas requisições deste endereço em pouco tempo.",
            hint=f"Aguarde {espera}s e tente de novo.",
            retryable=True,
            status_code=429,
        )
    marcas.append(agora)


def ip_do(request) -> str:
    """Atrás de proxy (Traefik/Caddy), o IP real vem no X-Forwarded-For.

    Só o **primeiro** valor interessa, e ainda assim é um dado que o cliente
    pode forjar quando o proxy não sobrescreve o header. Para limite de taxa
    isso é aceitável; para autorização, jamais.
    """
    encaminhado = request.headers.get("x-forwarded-for", "")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return request.client.host if request.client else "desconhecido"
