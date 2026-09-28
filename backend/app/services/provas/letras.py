"""Plano de letras das alternativas corretas — Núcleo Determinístico, puro.

quatro regras: diferença máxima de 1 entre quaisquer duas letras;
ausência de sequência de >= 3 respostas iguais; ausência de padrões repetitivos;
e <= 50% das posições com a mesma letra entre Provas A e B.

Gerar por embaralhamento e rejeitar, não construir. Medido: round-robin
deslocado (`ABCDEABCDE` contra `CDEABCDEAB`) satisfaz as regras 1, 2 e 4 para
todo (N, K) com ZERO colisões — e é exatamente o padrão que a regra 3 proíbe.
Backtracking em ordem lexicográfica devolve `AABBCCDDEE`, que é padrão também.
As regras 1, 2 e 4 são de graça; a dificuldade inteira está na regra 3.

A regra 3 é operacionalizada por famílias nomeadas de padrão, não por uma
definição fechada — o RF não dá uma, e nenhum conjunto finito de filtros a
fecharia. O que evita estrutura é o gerador ser embaralhamento; os filtros
existem para descartar o azar.
"""

from __future__ import annotations

import random
from itertools import pairwise

from backend.app.exceptions import PlanoDeLetrasImpossivelException
from backend.app.schemas.geracao import LETRAS

# Janela em que a deriva monótona é procurada. 5 é o menor valor medido que
# rejeita `AABBCCDDEE` e `EDCBA` sem inviabilizar nenhum (N, K) de 5 a 25.
JANELA_MONOTONA = 5

# Medido com os quatro filtros (período com último bloco truncado), o resto
# sorteado entre as letras e o plano da outra prova em `contra`, para todo n de
# 1 a 25, k de 2 a 11 e 20 sementes: zero casos inviáveis, média de 8,7
# tentativas, máximo de 616 em N=25 e K=3. Margem de três vezes.
MAX_TENTATIVAS_LETRAS = 2000

# "<= 50% das posições", como divisor inteiro: nunca ponto flutuante
# numa fronteira auditada.
LIMITE_COLISAO_DIVISOR = 2


def _multiconjunto_equilibrado(n: int, k: int, gerador: random.Random) -> list[int]:
    """Regra 1 por CONSTRUÇÃO, não por verificação: base para todas as letras,
    mais uma para `resto` letras SORTEADAS. Dar o resto sempre às primeiras
    letras sobrerrepresentava `A` em toda prova, e com 1 posição fazia A e B
    receberem a mesma letra com teto de colisão 0."""
    base, resto = divmod(n, k)
    extras = set(gerador.sample(range(k), resto))
    return [
        letra for letra in range(k) for _ in range(base + (1 if letra in extras else 0))
    ]


def tem_progressao_aritmetica(indices: list[int]) -> bool:
    """Regras 2 e 3 unificadas. O passo zero é `AAA`, que é literalmente a
    regra 2 do RF; o passo 1 é `ABC` e o passo 2 é `ACE`."""
    return any(
        indices[i + 1] - indices[i] == indices[i + 2] - indices[i + 1]
        for i in range(len(indices) - 2)
    )


def periodo_minimo(indices: list[int]) -> int:
    """Menor `p` tal que a sequência é o seu prefixo de `p` repetido, com o
    último bloco podendo ficar truncado. Não exige que `p` divida o comprimento:
    `ABDABDABDA` tem período 3, e exigir divisibilidade o deixava passar."""
    n = len(indices)
    for p in range(1, n):
        if all(indices[i] == indices[i % p] for i in range(n)):
            return p
    return n


def tem_deriva_monotona(indices: list[int], janela: int = JANELA_MONOTONA) -> bool:
    """Existe janela de `janela` posições consecutivas sem mudança de sinal na
    diferença? É o filtro que pega `AABBCCDDEE` e `EDCBA`.

    Escrito da forma óbvia, não incremental: é O(n²) com n <= 25, e o resultado
    é auditado — varredura de estado que ninguém reproduz à mão não serve, mesma
    razão da aritmética inteira nas.
    """
    for inicio in range(len(indices) - janela + 1):
        trecho = indices[inicio : inicio + janela]
        difs = [b - a for a, b in pairwise(trecho)]
        if all(d >= 0 for d in difs) or all(d <= 0 for d in difs):
            return True
    return False


def _aceitavel(
    indices: list[int], contra_indices: list[int] | None, limite_colisoes: int
) -> bool:
    n = len(indices)
    if tem_progressao_aritmetica(indices):
        return False
    if periodo_minimo(indices) * 2 <= n:
        return False
    if tem_deriva_monotona(indices):
        return False
    if contra_indices is not None:
        colisoes = sum(
            1 for x, y in zip(indices, contra_indices, strict=True) if x == y
        )
        if colisoes > limite_colisoes:
            return False
    return True


def planejar_letras(
    n_posicoes: int, k: int, semente: str, contra: list[str] | None = None
) -> list[str]:
    """Letras das corretas para as `n_posicoes` posições OBJETIVAS de uma prova.

    `contra` é o plano da outra prova, para a regra 4. `semente` derivada torna
    o plano reproduzível sem coluna de semente: o resultado persistido é
    `ItemProva.letra_atribuida`.
    """
    if n_posicoes == 0:
        # Prova só de discursivas é válida: nenhuma posição pede letra.
        return []
    contra_indices = (
        [LETRAS.index(letra) for letra in contra] if contra is not None else None
    )
    limite_colisoes = n_posicoes // LIMITE_COLISAO_DIVISOR
    gerador = random.Random(semente)
    for _ in range(MAX_TENTATIVAS_LETRAS):
        candidato = _multiconjunto_equilibrado(n_posicoes, k, gerador)
        gerador.shuffle(candidato)
        if _aceitavel(candidato, contra_indices, limite_colisoes):
            return [LETRAS[indice] for indice in candidato]
    raise PlanoDeLetrasImpossivelException(n_posicoes, k, MAX_TENTATIVAS_LETRAS)
