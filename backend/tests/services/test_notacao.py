import json
from pathlib import Path

import pytest

from backend.app.services.notacao import (
    Texto,
    comandos_fora_do_subconjunto,
    para_mathml,
    separar,
)

CASOS = json.loads(
    (Path(__file__).parents[3] / "frontend/src/test/fixtures/notacao.json").read_text(
        encoding="utf-8"
    )
)


def _como_dict(segmento):
    if isinstance(segmento, Texto):
        return {"tipo": "texto", "conteudo": segmento.conteudo}
    return {"tipo": "formula", "latex": segmento.latex, "destaque": segmento.destaque}


@pytest.mark.parametrize("caso", CASOS, ids=[c["nome"] for c in CASOS])
def test_separar_segue_o_fixture_compartilhado(caso):
    assert [_como_dict(s) for s in separar(caso["texto"])] == caso["segmentos"]


@pytest.mark.parametrize(
    "latex",
    [
        r"\frac{a}{b}",
        r"\sqrt[3]{x}",
        r"\sum_{i=1}^{n} i",
        r"\int_0^1 x\,dx".replace(r"\,", " "),
        r"\prod_{k=1}^{n} k",
        r"\lim_{x \to 0} f(x)",
        r"\alpha + \Omega",
        r"\mathrm{H_2SO_4} \rightleftharpoons \mathrm{H^+}",
        r"\left( a \right)",
        r"\begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix}",
        r"a \leq b \neq c \approx \infty \pm \partial \Delta",
    ],
)
def test_subconjunto_aceita_cada_construcao(latex):
    assert comandos_fora_do_subconjunto(latex) == []
    assert para_mathml(latex) is not None


@pytest.mark.parametrize(
    ("latex", "esperado"),
    [
        (r"\color{red}{x}", [r"\color"]),
        (r"\href{http://x}{y}", [r"\href"]),
        (r"\begin{align} a &= b \end{align}", [r"\begin{align}"]),
        (r"\newcommand{\a}{b}", [r"\newcommand"]),
    ],
)
def test_subconjunto_recusa(latex, esperado):
    assert comandos_fora_do_subconjunto(latex)[: len(esperado)] == esperado


def test_para_mathml_devolve_none_quando_nao_converte():
    # latex2mathml 3.78.0 aceita `\frac{a}`; recusa expoente sem operando.
    assert para_mathml("x^") is None
