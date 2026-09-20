"""Validação de parâmetros de geração — Núcleo Determinístico, nunca chama LLM."""

from backend.app.exceptions import ParametrosInconsistentesException


def validar_distribuicao(p_f: int, p_m: int, p_d: int) -> None:
    """pF + pM + pD deve somar exatamente 100% antes de qualquer geração."""
    if p_f + p_m + p_d != 100:
        raise ParametrosInconsistentesException(p_f, p_m, p_d)
