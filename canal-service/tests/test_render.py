import pytest

from app.errors import ApiError
from app.render import renderizar, variaveis_do_template


def test_renderiza_variaveis():
    corpo = "Oi {{nome}}, seu {{servico}} é {{data_hora}}."
    assert (
        renderizar(corpo, {"nome": "Ana", "servico": "corte", "data_hora": "quinta, 15h"})
        == "Oi Ana, seu corte é quinta, 15h."
    )


def test_variavel_faltando_nao_sai_com_buraco():
    with pytest.raises(ApiError) as exc:
        renderizar("Oi {{nome}}, {{data_hora}}.", {"nome": "Ana"})
    assert exc.value.code == "VARIAVEL_FALTANDO"
    assert "data_hora" in exc.value.message


def test_extrai_variaveis():
    assert variaveis_do_template("{{a}} x {{ b }} {{a}}") == {"a", "b"}
