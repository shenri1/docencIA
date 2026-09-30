"""Seleção das questões de cada prova — Núcleo Determinístico, puro.

N questões por prova, dificuldade balanceada pelo maior resto, e
sobreposição temática limitada entre as versões — no máximo 2 questões com o
mesmo subtema nas duas.

Medido: banco de 25 com 30/40/30 tem 7/10/8, e duas provas de 10 precisam 6/8/6,
então disjunto cabe. Mas um banco que perdeu 4 difíceis por âncora improdutiva
tem 7/10/4 e faltam 2 — e esse é o caso NORMAL depois de âncoras improdutivas e
exclusões. A sobreposição é a válvula de escape da distribuição, não um defeito.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass

from backend.app.domain import FaixaDificuldade, TipoQuestao
from backend.app.exceptions import (
    BancoInsuficienteParaProvaException,
    SobreposicaoInevitavelException,
)
from backend.app.models.banco import Questao
from backend.app.services.calculo_distribuicao_service import calcular_distribuicao

# "máximo 2 questões com o mesmo subtema em ambas", texto.
LIMITE_SUBTEMA_COMPARTILHADO = 2

MAX_TENTATIVAS_SELECAO = 2000

_FAIXAS = (FaixaDificuldade.FACIL, FaixaDificuldade.MEDIA, FaixaDificuldade.DIFICIL)
_TIPOS = (TipoQuestao.OBJETIVA, TipoQuestao.DISCURSIVA)

Celula = tuple[TipoQuestao, FaixaDificuldade]


@dataclass(frozen=True)
class Selecao:
    a: list[Questao]
    b: list[Questao]
    # Números das questões presentes nas DUAS provas.
    compartilhadas: list[int]
    # Selecionadas com subtema NULL: banco gerado antes desta etapa. A regra de
    # sobreposição está cega para elas, e o docente precisa saber.
    sem_subtema: int


def _baldes(questoes: list[Questao]) -> dict[Celula, list[Questao]]:
    """Agrupa por (tipo, faixa), em ordem de número — a ordem de partida é
    determinística antes de qualquer embaralhamento."""
    baldes: dict[Celula, list[Questao]] = {
        (tipo, faixa): [] for tipo in _TIPOS for faixa in _FAIXAS
    }
    for questao in sorted(questoes, key=lambda q: q.numero):
        baldes[(questao.tipo, questao.faixa_dificuldade)].append(questao)
    return baldes


def _divisoes(
    cotas: dict[FaixaDificuldade, int], n_objetivas: int, n_discursivas: int
) -> Iterator[dict[Celula, int]]:
    """Todas as matrizes 2×3 cujas somas por faixa são as cotas e cujas somas por
    tipo são as pedidas.

    Enumeração exaustiva de propósito: três faixas, cota de cada uma no máximo
    25. O espaço é minúsculo, e enumerar é auditável — heurística não é.
    """
    facil, media, dificil = _FAIXAS
    for o_facil in range(cotas[facil] + 1):
        for o_media in range(cotas[media] + 1):
            o_dificil = n_objetivas - o_facil - o_media
            if not 0 <= o_dificil <= cotas[dificil]:
                continue
            objetivas = {facil: o_facil, media: o_media, dificil: o_dificil}
            discursivas = {f: cotas[f] - objetivas[f] for f in _FAIXAS}
            if sum(discursivas.values()) != n_discursivas:
                continue
            yield {
                **{(TipoQuestao.OBJETIVA, f): objetivas[f] for f in _FAIXAS},
                **{(TipoQuestao.DISCURSIVA, f): discursivas[f] for f in _FAIXAS},
            }


def _sobreposicao_necessaria(
    divisao: dict[Celula, int], baldes: dict[Celula, list[Questao]]
) -> int:
    """Quantas questões teriam de aparecer nas duas provas, se esta divisão for
    usada. Zero quando cada célula tem o dobro do pedido."""
    return sum(
        max(0, 2 * pedido - len(baldes[celula])) for celula, pedido in divisao.items()
    )


def _escolher_divisao(
    cotas: dict[FaixaDificuldade, int],
    n_objetivas: int,
    n_discursivas: int,
    baldes: dict[Celula, list[Questao]],
) -> dict[Celula, int]:
    viaveis = [
        divisao
        for divisao in _divisoes(cotas, n_objetivas, n_discursivas)
        # Uma prova sozinha já precisa caber; a outra pode compartilhar.
        if all(pedido <= len(baldes[celula]) for celula, pedido in divisao.items())
    ]
    if not viaveis:
        raise BancoInsuficienteParaProvaException(
            cotas={faixa.value: cotas[faixa] for faixa in _FAIXAS},
            pedido_por_tipo={
                TipoQuestao.OBJETIVA.value: n_objetivas,
                TipoQuestao.DISCURSIVA.value: n_discursivas,
            },
            disponivel_por_celula={
                f"{tipo.value}/{faixa.value}": len(baldes[(tipo, faixa)])
                for tipo in _TIPOS
                for faixa in _FAIXAS
            },
        )
    # Critério declarado: minimiza a sobreposição necessária; empate
    # resolvido pela divisão lexicograficamente menor, para ser reproduzível.
    return min(
        viaveis,
        key=lambda d: (
            _sobreposicao_necessaria(d, baldes),
            tuple(d[(tipo, faixa)] for tipo in _TIPOS for faixa in _FAIXAS),
        ),
    )


def _repartir(
    balde: list[Questao], pedido: int, gerador: random.Random
) -> tuple[list[Questao], list[Questao], list[Questao]]:
    """(para_a, para_b, compartilhadas). Disjunto quando o balde tem o dobro."""
    sorteado = balde[:]
    gerador.shuffle(sorteado)
    if len(sorteado) >= 2 * pedido:
        return sorteado[:pedido], sorteado[pedido : 2 * pedido], []
    para_a = sorteado[:pedido]
    faltam = 2 * pedido - len(sorteado)
    # O rabo de A é reusado em B: o mínimo necessário, nunca mais.
    compartilhadas = para_a[:faltam]
    return para_a, sorteado[pedido:] + compartilhadas, compartilhadas


def _subtema_excedido(compartilhadas: list[Questao]) -> tuple[str, int] | None:
    """Subtema NULL nunca colide: duas questões sem subtema não são "o mesmo
    subtema", e tratá-las assim faria a regra parecer satisfeita quando está
    cega."""
    contagem = Counter(
        questao.subtema for questao in compartilhadas if questao.subtema is not None
    )
    for subtema, quantas in sorted(contagem.items()):
        if quantas > LIMITE_SUBTEMA_COMPARTILHADO:
            return subtema, quantas
    return None


def selecionar(
    questoes: list[Questao],
    n_objetivas: int,
    n_discursivas: int,
    p_f: int,
    p_m: int,
    p_d: int,
    semente: str,
) -> Selecao:
    distribuicao = calcular_distribuicao(n_objetivas + n_discursivas, p_f, p_m, p_d)
    cotas = {
        FaixaDificuldade.FACIL: distribuicao.faceis,
        FaixaDificuldade.MEDIA: distribuicao.medias,
        FaixaDificuldade.DIFICIL: distribuicao.dificeis,
    }
    baldes = _baldes(questoes)
    divisao = _escolher_divisao(cotas, n_objetivas, n_discursivas, baldes)

    gerador = random.Random(semente)
    excesso: tuple[str, int] | None = None
    for _ in range(MAX_TENTATIVAS_SELECAO):
        a: list[Questao] = []
        b: list[Questao] = []
        compartilhadas: list[Questao] = []
        for celula, pedido in divisao.items():
            if pedido == 0:
                continue
            para_a, para_b, comuns = _repartir(baldes[celula], pedido, gerador)
            a.extend(para_a)
            b.extend(para_b)
            compartilhadas.extend(comuns)
        excesso = _subtema_excedido(compartilhadas)
        if excesso is None:
            # Ordem dentro de cada prova também é sorteada: duas provas com as
            # mesmas questões em ordens diferentes é parte de serem paralelas.
            gerador.shuffle(a)
            gerador.shuffle(b)
            selecionadas = {questao.id: questao for questao in a + b}
            return Selecao(
                a=a,
                b=b,
                compartilhadas=sorted(questao.numero for questao in compartilhadas),
                sem_subtema=sum(
                    1 for questao in selecionadas.values() if questao.subtema is None
                ),
            )
    if excesso is None:  # só com MAX_TENTATIVAS_SELECAO < 1: o laço nem rodou
        raise RuntimeError("MAX_TENTATIVAS_SELECAO deve ser >= 1")
    subtema, quantas = excesso
    raise SobreposicaoInevitavelException(
        subtema, quantas, LIMITE_SUBTEMA_COMPARTILHADO
    )
