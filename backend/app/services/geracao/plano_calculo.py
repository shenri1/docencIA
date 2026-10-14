"""Plano das questões de cálculo — Núcleo Determinístico. Função
pura de (n, p_calculo, contagens por faixa): é o que mantém o plano igual na
retomada em lotes."""

from __future__ import annotations

from collections.abc import Sequence


def repartir(total: int, pesos: Sequence[int]) -> list[int]:
    """Método do maior resto. Desempate pela ordem dos pesos (fácil → difícil)."""
    soma = sum(pesos)
    if soma == 0 or total == 0:
        return [0] * len(pesos)
    pisos, restos = zip(*(divmod(total * p, soma) for p in pesos), strict=True)
    faltam = total - sum(pisos)
    ordem = sorted(range(len(pesos)), key=lambda i: (-restos[i], i))
    resultado = list(pisos)
    for i in ordem[:faltam]:
        resultado[i] += 1
    return resultado


def contagens_de_calculo(
    n_objetivas: int, p_calculo: int, por_faixa: Sequence[int]
) -> list[int]:
    """Quantas de cálculo em cada faixa. Dois termos [p, 100 − p] para o total;
    depois, proporcional às objetivas de cada faixa."""
    n_calculo = repartir(n_objetivas, [p_calculo, 100 - p_calculo])[0]
    return repartir(n_calculo, por_faixa)


def posicoes_de_calculo(n_faixa: int, c: int) -> set[int]:
    return {i * n_faixa // c for i in range(c)} if c else set()
