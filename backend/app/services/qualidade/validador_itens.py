"""Validador de forma dos itens — Núcleo Determinístico, nunca chama LLM.

Mede as regras (i)–(iv) e. A entrada é neutra
(`ItemAvaliavel`): a geração a monta a partir da saída do modelo, e a
auditoria da parte B vai montá-la a partir de uma Questao persistida. O
validador não conhece nenhum dos dois.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from backend.app.domain import RegraQualidade

# Listas fechadas em código de propósito: elas definem o que a métrica da
# mede, e mudá-las é mudança revisada, não configuração.
TERMOS_ABSOLUTOS = frozenset(
    {"sempre", "nunca", "jamais", "invariavelmente", "absolutamente"}
)
# "material", "trecho", "página" e "capítulo" ficam de fora: são conteúdo
# legítimo em várias disciplinas ("ponto material", "página de memória").
TERMOS_FONTE = frozenset(
    {"slide", "slides", "pdf", "livro", "livros", "aula", "aulas", "apostila"}
)

_PALAVRA = re.compile(r"\w+")


@dataclass(frozen=True)
class AlternativaAvaliavel:
    letra: str
    texto: str
    correta: bool
    e_gemeo_malvado: bool


@dataclass(frozen=True)
class ItemAvaliavel:
    enunciado: str
    alternativas: list[AlternativaAvaliavel]
    trechos_base: list[str]
    # Identificadores curtos dos materiais enviados ("P1", "S2"). Só esses
    # contam como menção de fonte: "cache L2" é conteúdo, não citação.
    identificadores_fonte: list[str]


@dataclass(frozen=True)
class Violacao:
    regra: RegraQualidade
    alvo: str
    detalhe: str

    def como_dict(self) -> dict[str, str]:
        return {"regra": self.regra.value, "alvo": self.alvo, "detalhe": self.detalhe}


def _normalizar(texto: str) -> str:
    """Sem acento e sem caixa: "Nunca" e "NUNCA" são o mesmo termo."""
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()


def _palavras(texto: str) -> list[str]:
    return _PALAVRA.findall(texto)


def _termos(texto: str) -> set[str]:
    # Palavra inteira: "sempreviva" não casa com "sempre".
    return {_normalizar(p) for p in _palavras(texto)}


def _decimal(valor: float) -> str:
    return f"{valor:.1f}".replace(".", ",")


def _textos(item: ItemAvaliavel) -> list[tuple[str, str]]:
    return [("enunciado", item.enunciado)] + [
        (a.letra, a.texto) for a in item.alternativas
    ]


def _tamanho_alternativa(item: ItemAvaliavel) -> list[Violacao]:
    contagens = [len(_palavras(a.texto)) for a in item.alternativas]
    total = sum(contagens)
    k = len(contagens)
    violacoes = []
    for alternativa, n in zip(item.alternativas, contagens, strict=True):
        demais = total - n
        # n > 1,5 × demais/(k-1), sem divisão: o resultado é auditado, e ponto
        # flutuante na fronteira exata produz violação irreproduzível à mão.
        if 2 * n * (k - 1) > 3 * demais:
            violacoes.append(
                Violacao(
                    RegraQualidade.TAMANHO_ALTERNATIVA,
                    alternativa.letra,
                    f"{alternativa.letra} tem {n} palavras; média das demais = "
                    f"{_decimal(demais / (k - 1))}",
                )
            )
    return violacoes


def _correta_longa(item: ItemAvaliavel) -> list[Violacao]:
    corretas = [a for a in item.alternativas if a.correta]
    erradas = [a for a in item.alternativas if not a.correta]
    if len(corretas) != 1 or not erradas:
        return []
    correta = corretas[0]
    n_correta = len(_palavras(correta.texto))
    maior = max(len(_palavras(a.texto)) for a in erradas)
    if 10 * n_correta > 12 * maior:
        return [
            Violacao(
                RegraQualidade.CORRETA_LONGA,
                correta.letra,
                f"a correta {correta.letra} tem {n_correta} palavras; a errada "
                f"mais longa tem {maior}",
            )
        ]
    return []


def _termo_absoluto(item: ItemAvaliavel) -> list[Violacao]:
    # "Sustentado pela fonte" vira "o termo aparece no trecho-base": mais
    # estrito que o juízo humano, mas auditável sem LLM.
    permitidos: set[str] = set()
    for trecho in item.trechos_base:
        permitidos |= _termos(trecho)
    violacoes = []
    for alvo, texto in _textos(item):
        encontrados = sorted((TERMOS_ABSOLUTOS & _termos(texto)) - permitidos)
        if encontrados:
            violacoes.append(
                Violacao(
                    RegraQualidade.TERMO_ABSOLUTO,
                    alvo,
                    f"usa {', '.join(encontrados)} sem sustentação no trecho-base",
                )
            )
    return violacoes


def _mencao_fonte(item: ItemAvaliavel) -> list[Violacao]:
    identificadores = {_normalizar(i): i for i in item.identificadores_fonte}
    proibidos = TERMOS_FONTE | identificadores.keys()
    violacoes = []
    for alvo, texto in _textos(item):
        encontrados = sorted(proibidos & _termos(texto))
        if encontrados:
            legiveis = [identificadores.get(t, t) for t in encontrados]
            violacoes.append(
                Violacao(
                    RegraQualidade.MENCAO_FONTE,
                    alvo,
                    f"menciona {', '.join(legiveis)} no corpo da questão",
                )
            )
    return violacoes


def _gemeos_insuficientes(item: ItemAvaliavel) -> list[Violacao]:
    k = len(item.alternativas)
    minimo = 1 if k <= 5 else 2
    # Confere a marcação declarada pelo modelo, não a semelhança estrutural
    # real — essa é juízo semântico, da auditoria da parte B.
    gemeos = sum(1 for a in item.alternativas if a.e_gemeo_malvado and not a.correta)
    if gemeos < minimo:
        return [
            Violacao(
                RegraQualidade.GEMEOS_INSUFICIENTES,
                "questao",
                f"{gemeos} gêmeo(s) malvado(s) entre as erradas; K={k} exige "
                f"ao menos {minimo}",
            )
        ]
    return []


def _gemeo_na_correta(item: ItemAvaliavel) -> list[Violacao]:
    return [
        Violacao(
            RegraQualidade.GEMEO_NA_CORRETA,
            a.letra,
            f"a correta {a.letra} está marcada como gêmeo malvado",
        )
        for a in item.alternativas
        if a.correta and a.e_gemeo_malvado
    ]


def validar_item(item: ItemAvaliavel) -> list[Violacao]:
    """Ordem determinística: a da tabela de regras, e dentro de cada
    regra, enunciado antes das alternativas, em ordem de letra."""
    return [
        *_tamanho_alternativa(item),
        *_correta_longa(item),
        *_termo_absoluto(item),
        *_mencao_fonte(item),
        *_gemeos_insuficientes(item),
        *_gemeo_na_correta(item),
    ]
