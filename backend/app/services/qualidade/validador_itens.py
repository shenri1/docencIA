"""Validador de forma dos itens — Núcleo Determinístico, nunca chama LLM.

Mede as regras (i)–(iv) e. A entrada é neutra
(`ItemObjetivo` ou `ItemDiscursivo`): a geração a monta a partir da saída do
modelo, e a auditoria da parte B vai montá-la a partir de uma Questao
persistida. O validador não conhece nenhum dos dois.
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

# Comando operacional da discursiva. Lista fechada em código, como as
# anteriores: define o que a métrica mede. Um falso positivo ("Qual a relação
# entre…?") vira violação registrada, não questão descartada.
VERBOS_COMANDO = frozenset(
    {
        "explique",
        "compare",
        "justifique",
        "descreva",
        "analise",
        "avalie",
        "discuta",
        "relacione",
        "diferencie",
        "demonstre",
        "argumente",
        "proponha",
        "elabore",
        "construa",
    }
)

_PALAVRA = re.compile(r"\w+")

# "alternativa B", "Letra (C)", "opção D". O substantivo ignora caixa; a letra
# NÃO — ela tem de ser maiúscula no texto original. Com tudo em minúscula, "a
# alternativa a ser marcada" casaria, porque o artigo "a" viraria a letra A.
# Lista fechada de propósito, como TERMOS_ABSOLUTOS: "B está errada", sem o
# substantivo, não é pego, e ampliar pegaria "a opção mais barata".
_CITACAO_LETRA = re.compile(
    r"(?i:\balternativa|\bletra|\bop[çc][ãa]o)\s+\(?[A-K]\)?(?!\w)"
)


@dataclass(frozen=True)
class AlternativaAvaliavel:
    letra: str
    texto: str
    correta: bool
    e_gemeo_malvado: bool


@dataclass(frozen=True)
class ItemObjetivo:
    enunciado: str
    alternativas: list[AlternativaAvaliavel]
    trechos_base: list[str]
    # Identificadores curtos dos materiais enviados ("P1", "S2"). Só esses
    # contam como menção de fonte: "cache L2" é conteúdo, não citação.
    identificadores_fonte: list[str]
    # Default None desliga as duas regras novas para quem não os
    # preenche — é o caso do auditor, que usa só as regras de assimetria.
    justificativa_correta: str | None = None
    texto_verificacao_unicidade: str | None = None
    # (letra original, motivo).
    invalidacoes: list[tuple[str, str]] | None = None


@dataclass(frozen=True)
class Violacao:
    regra: RegraQualidade
    alvo: str
    detalhe: str

    def como_dict(self) -> dict[str, str]:
        return {"regra": self.regra.value, "alvo": self.alvo, "detalhe": self.detalhe}


@dataclass(frozen=True)
class AspectoAvaliavel:
    texto: str
    trecho_base: str


@dataclass(frozen=True)
class ItemDiscursivo:
    enunciado: str
    aspectos: list[AspectoAvaliavel]
    identificadores_fonte: list[str]


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


def _textos(item: ItemObjetivo) -> list[tuple[str, str]]:
    return [("enunciado", item.enunciado)] + [
        (a.letra, a.texto) for a in item.alternativas
    ]


def _tamanho_alternativa(item: ItemObjetivo) -> list[Violacao]:
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


def _correta_longa(item: ItemObjetivo) -> list[Violacao]:
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


def _termo_absoluto(item: ItemObjetivo) -> list[Violacao]:
    # "Sustentado pela fonte" vira "o termo aparece no trecho-base": mais
    # estrito que o juízo humano, mas auditável sem LLM.
    violacoes = []
    for alvo, texto in _textos(item):
        violacoes.extend(_termo_absoluto_em(alvo, texto, item.trechos_base))
    return violacoes


def _mencao_fonte(item: ItemObjetivo) -> list[Violacao]:
    violacoes = []
    for alvo, texto in _textos(item):
        violacoes.extend(_mencao_fonte_em(alvo, texto, item.identificadores_fonte))
    return violacoes


def _gemeos_insuficientes(item: ItemObjetivo) -> list[Violacao]:
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


def _gemeo_na_correta(item: ItemObjetivo) -> list[Violacao]:
    return [
        Violacao(
            RegraQualidade.GEMEO_NA_CORRETA,
            a.letra,
            f"a correta {a.letra} está marcada como gêmeo malvado",
        )
        for a in item.alternativas
        if a.correta and a.e_gemeo_malvado
    ]


def cita_letra(texto: str) -> bool:
    """Pública: o gabarito marca o texto aprovado com ela, sem
    reescrevê-lo."""
    return _CITACAO_LETRA.search(texto) is not None


def _invalidacao_letra_invalida(item: ItemObjetivo) -> list[Violacao]:
    """O schema fecha cada letra por enum e fixa K-1 itens; não consegue impor
    letras distintas nem proibir a da correta."""
    if item.invalidacoes is None:
        return []
    letras = [letra for letra, _ in item.invalidacoes]
    correta = next((a.letra for a in item.alternativas if a.correta), None)
    erradas = sorted(a.letra for a in item.alternativas if not a.correta)
    if len(set(letras)) == len(letras) and correta not in letras:
        return []
    return [
        Violacao(
            RegraQualidade.INVALIDACAO_LETRA_INVALIDA,
            "questao",
            f"invalidações com letras {', '.join(letras)}; esperado uma para cada "
            f"errada ({', '.join(erradas)})",
        )
    ]


def _letra_citada_em_texto(item: ItemObjetivo) -> list[Violacao]:
    """A letra muda em cada versão da prova. Texto que a cita passa a
    apontar para a alternativa errada, e proíbe reescrevê-lo depois."""
    textos: list[tuple[str, str | None]] = [
        ("enunciado", item.enunciado),
        ("justificativa", item.justificativa_correta),
        ("unicidade", item.texto_verificacao_unicidade),
        *((f"invalidacao {letra}", motivo) for letra, motivo in item.invalidacoes or []),
    ]
    return [
        Violacao(
            RegraQualidade.LETRA_CITADA_EM_TEXTO,
            alvo,
            "cita letra de alternativa; a letra muda em cada versão da prova",
        )
        for alvo, texto in textos
        if texto is not None and cita_letra(texto)
    ]


def validar_objetiva(item: ItemObjetivo) -> list[Violacao]:
    """Ordem determinística: a da tabela de regras, e dentro de cada
    regra, enunciado antes das alternativas, em ordem de letra."""
    return [
        *_tamanho_alternativa(item),
        *_correta_longa(item),
        *_termo_absoluto(item),
        *_mencao_fonte(item),
        *_gemeos_insuficientes(item),
        *_gemeo_na_correta(item),
        *_invalidacao_letra_invalida(item),
        *_letra_citada_em_texto(item),
    ]


def _termo_absoluto_em(
    alvo: str, texto: str, trechos_base: list[str]
) -> list[Violacao]:
    permitidos: set[str] = set()
    for trecho in trechos_base:
        permitidos |= _termos(trecho)
    encontrados = sorted((TERMOS_ABSOLUTOS & _termos(texto)) - permitidos)
    if not encontrados:
        return []
    return [
        Violacao(
            RegraQualidade.TERMO_ABSOLUTO,
            alvo,
            f"usa {', '.join(encontrados)} sem sustentação no trecho-base",
        )
    ]


def _mencao_fonte_em(
    alvo: str, texto: str, identificadores_fonte: list[str]
) -> list[Violacao]:
    identificadores = {_normalizar(i): i for i in identificadores_fonte}
    encontrados = sorted((TERMOS_FONTE | identificadores.keys()) & _termos(texto))
    if not encontrados:
        return []
    legiveis = [identificadores.get(t, t) for t in encontrados]
    return [
        Violacao(
            RegraQualidade.MENCAO_FONTE,
            alvo,
            f"menciona {', '.join(legiveis)} no corpo da questão",
        )
    ]


def _comando_ausente(item: ItemDiscursivo) -> list[Violacao]:
    if VERBOS_COMANDO & _termos(item.enunciado):
        return []
    return [
        Violacao(
            RegraQualidade.COMANDO_AUSENTE,
            "enunciado",
            "nenhum verbo de comando operacional (explique, compare, justifique…)",
        )
    ]


def _aspectos_repetidos(item: ItemDiscursivo) -> list[Violacao]:
    vistos: dict[tuple[str, ...], int] = {}
    violacoes = []
    for ordem, aspecto in enumerate(item.aspectos, start=1):
        # Sequência de palavras normalizadas: pontuação e espaço extra não
        # distinguem dois aspectos iguais.
        chave = tuple(_normalizar(p) for p in _palavras(aspecto.texto))
        if chave in vistos:
            violacoes.append(
                Violacao(
                    RegraQualidade.ASPECTOS_REPETIDOS,
                    f"aspecto {ordem}",
                    f"repete o aspecto {vistos[chave]}",
                )
            )
        else:
            vistos[chave] = ordem
    return violacoes


def validar_discursiva(item: ItemDiscursivo) -> list[Violacao]:
    """Só forma. "O enunciado revela os aspectos" e "o aspecto é observável"
    são juízo semântico — do crítico e do docente. Aspectos ficam fora de
    termo absoluto e menção de fonte: são para o docente, não para o aluno."""
    trechos = [a.trecho_base for a in item.aspectos]
    return [
        *_termo_absoluto_em("enunciado", item.enunciado, trechos),
        *_mencao_fonte_em("enunciado", item.enunciado, item.identificadores_fonte),
        *_comando_ausente(item),
        *_aspectos_repetidos(item),
    ]
