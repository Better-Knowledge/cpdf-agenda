from datetime import UTC, datetime

import pytest

from app.errors import ApiError
from app.tempo import TZ, exigir_aware, label_humano


def test_label_humano_em_portugues():
    # 2026-05-14 é uma quinta-feira
    dt = datetime(2026, 5, 14, 15, 30, tzinfo=TZ)
    assert label_humano(dt) == "quinta, 14 de maio, 15h30"


def test_label_humano_hora_cheia_e_conversao_de_fuso():
    dt = datetime(2026, 5, 14, 18, 0, tzinfo=UTC)  # 15h locais
    assert label_humano(dt) == "quinta, 14 de maio, 15h"


def test_datetime_naive_e_proibido():
    with pytest.raises(ApiError) as exc:
        exigir_aware(datetime(2026, 5, 14, 15, 30))
    assert exc.value.code == "DATA_SEM_FUSO"
