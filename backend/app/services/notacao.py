"""Gramática da notação matemática e química — Núcleo
Determinístico, nunca chama LLM.

O texto é gravado como o modelo escreveu, com o LaTeX dentro. Quem interpreta é a
renderização (KaTeX na tela, OMML no DOCX). Esta é a única definição do
subconjunto: o validador e o DOCX importam daqui, e `frontend/src/lib/formulas.ts`
reproduz `separar` contra o mesmo `notacao.json`.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import latex2mathml.converter

_GREGAS_MINUSCULAS = [
    "alpha",
    "beta",
    "gamma",
    "delta",
    "epsilon",
    "varepsilon",
    "zeta",
    "eta",
    "theta",
    "vartheta",
    "iota",
    "kappa",
    "lambda",
    "mu",
    "nu",
    "xi",
    "pi",
    "rho",
    "sigma",
    "tau",
    "upsilon",
    "phi",
    "varphi",
    "chi",
    "psi",
    "omega",
]
_GREGAS_MAIUSCULAS = [
    "Gamma",
    "Delta",
    "Theta",
    "Lambda",
    "Xi",
    "Pi",
    "Sigma",
    "Upsilon",
    "Phi",
    "Psi",
    "Omega",
]

COMANDOS_PERMITIDOS = frozenset(
    {
        "frac",
        "sqrt",
        "sum",
        "int",
        "prod",
        "lim",
        "mathrm",
        "text",
        "cdot",
        "times",
        "pm",
        "leq",
        "geq",
        "neq",
        "approx",
        "infty",
        "partial",
        "to",
        "rightarrow",
        "leftarrow",
        "rightleftharpoons",
        "left",
        "right",
        "begin",
        "end",
        *_GREGAS_MINUSCULAS,
        *_GREGAS_MAIUSCULAS,
    }
)
AMBIENTES_PERMITIDOS = frozenset({"pmatrix", "bmatrix"})


@dataclass(frozen=True)
class Texto:
    conteudo: str


@dataclass(frozen=True)
class Formula:
    latex: str
    destaque: bool


# `+?`: delimitador vazio fica texto. DOTALL: a quebra de linha dentro de `\(...\)`
# é tarefa do validador (caso 5), não da separação.
_FORMULA = re.compile(r"\\\((?P<linha>.+?)\\\)|\\\[(?P<destaque>.+?)\\\]", re.DOTALL)
_COMANDO = re.compile(r"\\([A-Za-z]+)")
_AMBIENTE = re.compile(r"\\(?:begin|end)\{([^}]*)\}")


def separar(texto: str) -> list[Texto | Formula]:
    segmentos: list[Texto | Formula] = []
    posicao = 0
    for achado in _FORMULA.finditer(texto):
        if achado.start() > posicao:
            segmentos.append(Texto(texto[posicao : achado.start()]))
        if achado.group("linha") is not None:
            segmentos.append(Formula(achado.group("linha"), destaque=False))
        else:
            segmentos.append(Formula(achado.group("destaque"), destaque=True))
        posicao = achado.end()
    if posicao < len(texto):
        segmentos.append(Texto(texto[posicao:]))
    return segmentos


def comandos_fora_do_subconjunto(latex: str) -> list[str]:
    fora: list[str] = []
    for nome in _COMANDO.findall(latex):
        rotulo = f"\\{nome}"
        if nome not in COMANDOS_PERMITIDOS and rotulo not in fora:
            fora.append(rotulo)
    for ambiente in _AMBIENTE.findall(latex):
        rotulo = f"\\begin{{{ambiente}}}"
        if ambiente not in AMBIENTES_PERMITIDOS and rotulo not in fora:
            fora.append(rotulo)
    return fora


def para_mathml(latex: str) -> ET.Element | None:
    """O latex2mathml levanta tipos de exceção diferentes por versão; qualquer
    falha é "não converte"."""
    try:
        return ET.fromstring(latex2mathml.converter.convert(latex))
    except Exception:  # noqa: BLE001
        return None
