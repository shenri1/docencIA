"""AST → LaTeX da resolução. Só o subconjunto da `\\ln` e
afins não existem lá, então saem em `\\mathrm{}`; módulo usa `\\left| \\right|`."""

from __future__ import annotations

import ast

from backend.app.services.notacao import COMANDOS_PERMITIDOS

_GREGAS = {
    c
    for c in COMANDOS_PERMITIDOS
    if c[0].isalpha()
    and c
    not in {
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
    }
}


def _base(base: str) -> str:
    if base in _GREGAS:
        return f"\\{base}"
    if len(base) == 1:
        return base
    return f"\\mathrm{{{base}}}"


def simbolo_latex(nome: str) -> str:
    base, _, resto = nome.partition("_")
    return f"{_base(base)}_{{{resto}}}" if resto else _base(base)


# Precedência: soma/subtração 1, produto 2, unário 3, potência 4, átomo 5.
def _prec(no: ast.AST) -> int:
    if isinstance(no, ast.BinOp):
        return {ast.Add: 1, ast.Sub: 1, ast.Mult: 2, ast.Div: 2, ast.Pow: 4}[
            type(no.op)
        ]
    if isinstance(no, ast.UnaryOp):
        return 3
    return 5


def _numero(valor) -> str:
    texto = repr(float(valor)) if isinstance(valor, float) else str(valor)
    texto = texto.removesuffix(".0")
    return texto.replace(".", "{,}")


def _com_parenteses(no: ast.AST, minimo: int, valores: dict[str, str]) -> str:
    texto = _expr(no, valores)
    if _prec(no) < minimo:
        return f"\\left( {texto} \\right)"
    return texto


def _expr(no: ast.AST, valores: dict[str, str]) -> str:
    if isinstance(no, ast.Constant):
        return _numero(no.value)
    if isinstance(no, ast.Name):
        if no.id == "pi":
            return "\\pi"
        return valores.get(no.id, simbolo_latex(no.id))
    if isinstance(no, ast.UnaryOp):
        sinal = "-" if isinstance(no.op, ast.USub) else ""
        return sinal + _com_parenteses(no.operand, 4, valores)
    if isinstance(no, ast.BinOp):
        if isinstance(no.op, ast.Div):
            return f"\\frac{{{_expr(no.left, valores)}}}{{{_expr(no.right, valores)}}}"
        if isinstance(no.op, ast.Pow):
            base = _com_parenteses(no.left, 5, valores)
            return f"{base}^{{{_expr(no.right, valores)}}}"
        if isinstance(no.op, ast.Mult):
            return f"{_com_parenteses(no.left, 2, valores)} \\cdot {_com_parenteses(no.right, 3, valores)}"
        operador = "+" if isinstance(no.op, ast.Add) else "-"
        direita = _com_parenteses(no.right, 2 if operador == "-" else 1, valores)
        return f"{_expr(no.left, valores)} {operador} {direita}"
    if isinstance(no, ast.Call):
        nome = no.func.id
        arg = _expr(no.args[0], valores)
        if nome == "sqrt":
            return f"\\sqrt{{{arg}}}"
        if nome == "abs":
            return f"\\left| {arg} \\right|"
        if nome == "exp":
            return f"\\mathrm{{e}}^{{{arg}}}"
        rotulo = "log_{10}" if nome == "log10" else nome
        return f"\\mathrm{{{rotulo}}}\\left( {arg} \\right)"
    raise ValueError(f"nó fora da lista: {type(no).__name__}")


def resolucao_latex(
    expressao: str,
    valores: dict[str, str],
    unidade_resultado_ltx: str,
    resultado_fmt: str,
    simbolo: str | None,
) -> str:
    """`valores`: símbolo → valor já formatado. Símbolo sem valor sai como
    símbolo. A expressão já passou pelo avaliador, então a árvore é segura."""
    arvore = ast.parse(expressao.strip(), mode="eval").body
    corpo = _expr(arvore, valores)
    final = (
        resultado_fmt
        if not unidade_resultado_ltx
        else f"{resultado_fmt}\\ {unidade_resultado_ltx}"
    )
    prefixo = f"{simbolo_latex(simbolo)} = " if simbolo else ""
    return f"{prefixo}{corpo} = {final}"
