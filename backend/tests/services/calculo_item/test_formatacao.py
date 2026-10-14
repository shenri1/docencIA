import pytest

from backend.app.services.calculo_item.formatacao import (
    formatar_valor,
    unidade_latex,
    valor_com_unidade,
)
from backend.app.services.notacao import comandos_fora_do_subconjunto, para_mathml


@pytest.mark.parametrize(
    ("x", "esperado"),
    [
        (9.8995, "9{,}90"),
        (123.456, "123"),
        (0.0123456, "0{,}0123"),
        (999.5, "1000"),  # arredonda para cima e continua posicional
        (0.001, "0{,}00100"),  # fronteira inferior: ainda posicional
        # Arredonda para 1,00e-3 e cai na fronteira: posicional, como 0,001.
        (0.00099996, "0{,}00100"),
        (999999.6, r"1{,}00 \times 10^{6}"),  # fronteira superior: científica
        (123456.0, "123000"),
        (0.000123456, r"1{,}23 \times 10^{-4}"),
        (-2.5, "-2{,}50"),
        (0.0, "0"),
    ],
)
def test_tres_algarismos(x, esperado):
    assert formatar_valor(x) == esperado


def test_dados_aparam_zeros():
    assert formatar_valor(9.81, algarismos=6, aparar=True) == "9{,}81"
    assert formatar_valor(5.0, algarismos=6, aparar=True) == "5"
    assert formatar_valor(101325.0, algarismos=6, aparar=True) == "101325"


@pytest.mark.parametrize(
    "unidade", ["m/s", "m/s**2", "mol/L", "kg", "J/(mol*K)", "dimensionless", ""]
)
def test_unidade_em_latex_dentro_do_subconjunto(unidade):
    ltx = unidade_latex(unidade)
    assert ltx is not None
    assert comandos_fora_do_subconjunto(ltx) == []
    assert para_mathml(rf"1\ {ltx}") is not None


def test_valor_com_unidade_sem_unidade_e_so_o_valor():
    assert valor_com_unidade("9{,}90", "") == "9{,}90"
    assert valor_com_unidade("9{,}90", r"\mathrm{m}") == r"9{,}90\ \mathrm{m}"
