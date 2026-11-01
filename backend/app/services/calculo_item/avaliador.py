"""Avaliador de expressões de cálculo — Núcleo
Determinístico, nunca chama LLM.

A expressão vem do modelo. Nada de `eval`: o texto é lido com `ast.parse` e a
árvore é percorrida com uma lista fechada de nós e de funções. As grandezas são
`pint.Quantity` de um registro único, e a dimensão é checada em cada operação.
"""

from __future__ import annotations

import ast
import math
import re

import pint

from backend.app.domain import RegraQualidade

UREG = pint.UnitRegistry()
# pint 0.25 nem sempre levanta PintError: converter para unidade logarítmica
# composta ("dB/km", "dBm/Hz") cai num `assert` interno. Para o avaliador, as
# duas coisas são a mesma: a unidade não fecha, e o crítico corrige.
_ERROS_DO_PINT = (pint.errors.PintError, AssertionError)

MAX_CARACTERES = 300
MAX_PROFUNDIDADE = 30
MAX_EXPOENTE = 100
FUNCOES = frozenset({"sqrt", "exp", "ln", "log10", "sin", "cos", "tan", "abs"})
RESERVADOS = FUNCOES | {"pi"}
_SIMBOLO = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def SIMBOLO_VALIDO(nome: str) -> bool:
    return bool(_SIMBOLO.fullmatch(nome)) and nome not in RESERVADOS


class ErroCalculo(Exception):
    def __init__(self, regra: RegraQualidade, detalhe: str):
        super().__init__(detalhe)
        self.regra = regra
        self.detalhe = detalhe


def _invalida(detalhe: str) -> ErroCalculo:
    return ErroCalculo(RegraQualidade.EXPRESSAO_INVALIDA, detalhe)


def _dimensao(detalhe: str) -> ErroCalculo:
    return ErroCalculo(RegraQualidade.DIMENSAO_INCOERENTE, detalhe)


def quantidade(valor: float, unidade: str) -> pint.Quantity:
    """`unidade` vazia é grandeza sem dimensão."""
    if not math.isfinite(valor):
        raise _invalida("valor não finito")
    try:
        return (
            UREG.Quantity(float(valor), unidade)
            if unidade.strip()
            else UREG.Quantity(float(valor))
        )
    except _ERROS_DO_PINT as exc:
        raise _dimensao(f"unidade desconhecida “{unidade}”: {exc}") from exc
    except Exception as exc:
        raise _dimensao(f"unidade inválida “{unidade}”") from exc


def _sem_dimensao(q: pint.Quantity, onde: str) -> float:
    try:
        return float(q.to("dimensionless").magnitude)
    except _ERROS_DO_PINT as exc:
        raise _dimensao(
            f"{onde} exige argumento sem dimensão, recebeu {q.units}"
        ) from exc


def _angulo(q: pint.Quantity, onde: str) -> float:
    try:
        return float(q.to("radian").magnitude)
    except _ERROS_DO_PINT as exc:
        raise _dimensao(f"{onde} exige ângulo, recebeu {q.units}") from exc


def _no(no: ast.AST, valores: dict[str, pint.Quantity], nivel: int) -> pint.Quantity:
    if nivel > MAX_PROFUNDIDADE:
        raise _invalida(
            f"expressão aninhada demais (mais de {MAX_PROFUNDIDADE} níveis)"
        )
    if isinstance(no, ast.Constant):
        if isinstance(no.value, bool) or not isinstance(no.value, int | float):
            raise _invalida(f"constante não numérica: {no.value!r}")
        return UREG.Quantity(float(no.value))
    if isinstance(no, ast.Name):
        if no.id == "pi":
            return UREG.Quantity(math.pi)
        if no.id not in valores:
            raise _invalida(f"símbolo não declarado em dados: {no.id}")
        return valores[no.id]
    if isinstance(no, ast.UnaryOp) and isinstance(no.op, ast.UAdd | ast.USub):
        operando = _no(no.operand, valores, nivel + 1)
        return -operando if isinstance(no.op, ast.USub) else operando
    if isinstance(no, ast.BinOp):
        esquerda = _no(no.left, valores, nivel + 1)
        direita = _no(no.right, valores, nivel + 1)
        if isinstance(no.op, ast.Add):
            return esquerda + direita
        if isinstance(no.op, ast.Sub):
            return esquerda - direita
        if isinstance(no.op, ast.Mult):
            return esquerda * direita
        if isinstance(no.op, ast.Div):
            return esquerda / direita
        if isinstance(no.op, ast.Pow):
            expoente = _sem_dimensao(direita, "expoente")
            if abs(expoente) > MAX_EXPOENTE:
                raise _invalida(f"expoente {expoente:g} acima de {MAX_EXPOENTE}")
            return esquerda**expoente
        raise _invalida(f"operador não permitido: {type(no.op).__name__}")
    if isinstance(no, ast.Call):
        if (
            not isinstance(no.func, ast.Name)
            or no.func.id not in FUNCOES
            or no.keywords
            or len(no.args) != 1
        ):
            raise _invalida("chamada não permitida")
        nome = no.func.id
        arg = _no(no.args[0], valores, nivel + 1)
        if nome == "sqrt":
            return arg**0.5
        if nome == "abs":
            return abs(arg)
        if nome in {"sin", "cos", "tan"}:
            f = {"sin": math.sin, "cos": math.cos, "tan": math.tan}[nome]
            return UREG.Quantity(f(_angulo(arg, nome)))
        x = _sem_dimensao(arg, nome)
        f = {"exp": math.exp, "ln": math.log, "log10": math.log10}[nome]
        return UREG.Quantity(f(x))
    raise _invalida(f"construção não permitida: {type(no).__name__}")


def avaliar(expressao: str, valores: dict[str, pint.Quantity]) -> pint.Quantity:
    if len(expressao) > MAX_CARACTERES:
        raise _invalida(f"expressão com mais de {MAX_CARACTERES} caracteres")
    try:
        arvore = ast.parse(expressao.strip(), mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        raise _invalida(f"sintaxe inválida: {exc}") from exc
    try:
        resultado = _no(arvore.body, valores, 1)
        magnitude = resultado.magnitude
    except ErroCalculo:
        raise
    except _ERROS_DO_PINT as exc:
        raise _dimensao(str(exc)) from exc
    except (ZeroDivisionError, OverflowError, ValueError) as exc:
        raise _invalida(f"não calculável: {exc}") from exc
    if isinstance(magnitude, complex) or not math.isfinite(magnitude):
        raise _invalida("resultado não finito")
    return resultado


def em_unidade(q: pint.Quantity, unidade: str) -> float:
    try:
        valor = float(q.to(unidade if unidade.strip() else "dimensionless").magnitude)
    except _ERROS_DO_PINT as exc:
        raise _dimensao(
            f"o resultado ({q.units}) não converte para “{unidade}”: {exc}"
        ) from exc
    except (ZeroDivisionError, OverflowError, ValueError) as exc:
        # Unidade logarítmica (dB) com razão ≤ 0: o log do pint levanta
        # ValueError. Mesma classificação de `avaliar`: não calculável.
        raise _invalida(f"não calculável em “{unidade}”: {exc}") from exc
    if not math.isfinite(valor):
        raise _invalida("resultado não finito")
    return valor
