import pytest

from backend.app.services.calculo_item.latex import resolucao_latex, simbolo_latex
from backend.app.services.notacao import comandos_fora_do_subconjunto, para_mathml


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("x", "x"),
        ("v_0", "v_{0}"),
        ("E_a", "E_{a}"),
        ("Ea", r"\mathrm{Ea}"),
        ("theta", r"\theta"),
        ("Delta_H", r"\Delta_{H}"),
        ("Delta", r"\Delta"),
        ("kB", r"\mathrm{kB}"),
    ],
)
def test_simbolo_latex(nome, esperado):
    assert simbolo_latex(nome) == esperado


def test_resolucao_substitui_os_valores():
    ltx = resolucao_latex(
        "sqrt(2 * g * h)",
        {"g": "9{,}8", "h": "5"},
        r"\frac{\mathrm{m}}{\mathrm{s}}",
        "9{,}90",
        "v",
    )
    assert ltx == (
        r"v = \sqrt{2 \cdot 9{,}8 \cdot 5} = 9{,}90\ "
        r"\frac{\mathrm{m}}{\mathrm{s}}"
    )


@pytest.mark.parametrize(
    "expressao",
    [
        "a / b",
        "a ** 2",
        "(a + b) * c",
        "-a",
        "abs(a)",
        "ln(a)",
        "log10(a)",
        "exp(a)",
        "sin(a)",
        "2 * pi * a",
        "(a + b) ** 2 / c ** 0.5",
    ],
)
def test_toda_resolucao_cabe_no_subconjunto_e_converte(expressao):
    ltx = resolucao_latex(expressao, {}, "", "1", None)
    assert comandos_fora_do_subconjunto(ltx) == []
    assert para_mathml(ltx) is not None
