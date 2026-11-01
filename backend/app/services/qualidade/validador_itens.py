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
from difflib import SequenceMatcher

from backend.app.domain import FaixaDificuldade, FormatoItem, RegraQualidade
from backend.app.services.notacao import (
    Formula,
    Texto,
    comandos_fora_do_subconjunto,
    para_mathml,
    separar,
)

# Listas fechadas em código de propósito: elas definem o que a métrica da
# Mede, e mudá-las é mudança revisada, não configuração.
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
# "discuta", "comente" e "discorra" ficam fora: verbo vago não diz o que fazer.
VERBOS_COMANDO = frozenset(
    {
        "explique",
        "compare",
        "justifique",
        "descreva",
        "analise",
        "avalie",
        "relacione",
        "diferencie",
        "demonstre",
        "argumente",
        "proponha",
        "elabore",
        "construa",
        "interprete",
        "exemplifique",
        "classifique",
        "resuma",
        "infira",
        "caracterize",
        "resolva",
        "calcule",
        "determine",
        "aplique",
        "examine",
        "organize",
        "contraste",
        "critique",
        "julgue",
        "recomende",
        "planeje",
        "formule",
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


# Regras dos guias de elaboração. Listas fechadas em código, como as
# anteriores, comparadas sem acento e sem caixa, por sequência de palavras.
TERMOS_ALTERNATIVA_GENERICA = (
    "todas as anteriores",
    "nenhuma das anteriores",
    "todas as alternativas",
    "nenhuma das alternativas",
    "todas estao corretas",
    "nenhuma esta correta",
    "todas as opcoes",
    "nenhuma das opcoes",
)
TERMOS_NEGATIVOS = frozenset(
    {"incorreta", "incorreto", "incorretas", "incorretos", "exceto", "nao"}
)
TERMOS_OPINIAO = (
    "sua opiniao",
    "voce acha",
    "voce concorda",
    "voce pensa",
    "seu ponto de vista",
    "na sua visao",
)
# Abaixo disso a alternativa é rótulo ("Usa fila."). Alternativa que contém
# fórmula é isenta; "12 m/s" é das questões de cálculo.
MINIMO_PALAVRAS_ALTERNATIVA = 4
# A fácil não tem mínimo: pergunta direta é permitida.
MINIMO_PALAVRAS_CONTEXTO = {FaixaDificuldade.MEDIA: 15, FaixaDificuldade.DIFICIL: 40}
# Limiar próprio da asserção: mais baixo que o LIMIAR_ENUNCIADO_REPETIDO (0,9).
LIMIAR_ASSERCAO_CITACAO = 0.8


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
    # Defaults desligam as regras novas para quem não os preenche — o
    # auditor monta o item de uma Questao persistida, que só tem o enunciado.
    formato: FormatoItem = FormatoItem.PROPOSICAO
    faixa: FaixaDificuldade | None = None
    contexto: str | None = None
    comando: str | None = None
    # Asserção e razão, só em ASSERCAO_RAZAO.
    assercoes: list[str] | None = None
    # Só no formato CALCULO.
    formula_citada: str | None = None
    # (símbolo, valor, unidade), com o valor já arredondado.
    dados_calculo: list[tuple[str, float, str]] | None = None
    # Texto dos trechos ENVIADOS ao modelo, não só das fontes que ele citou.
    texto_dos_trechos: list[str] | None = None


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
    faixa: FaixaDificuldade | None = None
    contexto: str | None = None
    # (alvo, comando) por item: ("item a", …). None = sem itens: mede o enunciado.
    comandos: list[tuple[str, str]] | None = None


def _normalizar(texto: str) -> str:
    """Sem acento e sem caixa: "Nunca" e "NUNCA" são o mesmo termo."""
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()


def _palavras(texto: str) -> list[str]:
    return _PALAVRA.findall(texto)


# A cópia medida no uso real era idêntica (razão 1,0). Subido de 0,8
# para 0,9 (2026-10-09): o 0,8 recusava variação legítima; a cópia literal
# ainda é pega com folga.
LIMIAR_ENUNCIADO_REPETIDO = 0.9


def _semelhanca(a: str, b: str) -> float:
    pa = [_normalizar(p) for p in _palavras(a)]
    pb = [_normalizar(p) for p in _palavras(b)]
    return SequenceMatcher(None, pa, pb).ratio()


def enunciado_repetido(candidato: str, original: str) -> bool:
    """Substituição: o rascunho repete o enunciado da original?
    Compara a sequência de palavras normalizadas, então caixa, acento e
    pontuação não disfarçam a cópia."""
    return _semelhanca(candidato, original) >= LIMIAR_ENUNCIADO_REPETIDO


def _frases(texto: str, termos: tuple[str, ...]) -> list[str]:
    """Termos de várias palavras, por palavra inteira e sem acento."""
    normalizado = " " + " ".join(_normalizar(p) for p in _palavras(texto)) + " "
    return [t for t in termos if f" {t} " in normalizado]


def _termos(texto: str) -> set[str]:
    # Palavra inteira: "sempreviva" não casa com "sempre".
    return {_normalizar(p) for p in _palavras(texto)}


def _decimal(valor: float) -> str:
    return f"{valor:.1f}".replace(".", ",")


def _textos(item: ItemObjetivo) -> list[tuple[str, str]]:
    textos = [("enunciado", item.enunciado)]
    if item.formato is FormatoItem.PROPOSICAO:
        # Nos formatos montados, as alternativas são texto do sistema.
        textos += [(a.letra, a.texto) for a in item.alternativas]
    return textos


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
    apontar para a alternativa errada, e a exportação fiel proíbe reescrevê-lo depois."""
    textos: list[tuple[str, str | None]] = [
        ("enunciado", item.enunciado),
        ("justificativa", item.justificativa_correta),
        ("unicidade", item.texto_verificacao_unicidade),
        *(
            (f"invalidacao {letra}", motivo)
            for letra, motivo in item.invalidacoes or []
        ),
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


def _proposicao_com_comando(item: ItemObjetivo) -> bool:
    return item.formato is FormatoItem.PROPOSICAO and item.comando is not None


def _alternativa_rotulo(item: ItemObjetivo) -> list[Violacao]:
    if not _proposicao_com_comando(item):
        return []
    violacoes = []
    for alternativa in item.alternativas:
        n = len(_palavras(alternativa.texto))
        if n < MINIMO_PALAVRAS_ALTERNATIVA and not _contem_formula(alternativa.texto):
            violacoes.append(
                Violacao(
                    RegraQualidade.ALTERNATIVA_ROTULO,
                    alternativa.letra,
                    f"{alternativa.letra} tem {n} palavras; alternativa é afirmação "
                    f"completa, com ao menos {MINIMO_PALAVRAS_ALTERNATIVA}",
                )
            )
    return violacoes


def _alternativa_generica(item: ItemObjetivo) -> list[Violacao]:
    if not _proposicao_com_comando(item):
        return []
    return [
        Violacao(
            RegraQualidade.ALTERNATIVA_GENERICA,
            alternativa.letra,
            f"usa “{termos[0]}”; a permutação das provas muda o que ela indica",
        )
        for alternativa in item.alternativas
        if (termos := _frases(alternativa.texto, TERMOS_ALTERNATIVA_GENERICA))
    ]


def _inicial(texto: str) -> str | None:
    """'maiuscula', 'minuscula' ou None — sigla (TCP), número e símbolo, como o
    `\\(`, não dizem nada sobre a pontuação do comando."""
    palavras = texto.split()
    if not palavras or not palavras[0][0].isalpha():
        return None
    letras = [c for c in palavras[0] if c.isalpha()]
    if len(letras) >= 2 and all(c.isupper() for c in letras):
        return None
    return "maiuscula" if palavras[0][0].isupper() else "minuscula"


def _pontuacao_incoerente(item: ItemObjetivo) -> list[Violacao]:
    if not _proposicao_com_comando(item):
        return []
    fim = item.comando.rstrip()[-1:]
    if fim == "?":
        proibida, detalhe = (
            "minuscula",
            "o comando é pergunta, e a alternativa começa com minúscula",
        )
    elif fim in (".", ":", "!"):
        return []
    else:
        proibida, detalhe = (
            "maiuscula",
            "o comando é frase incompleta, e a alternativa começa com maiúscula",
        )
    return [
        Violacao(RegraQualidade.PONTUACAO_INCOERENTE, a.letra, detalhe)
        for a in item.alternativas
        if _inicial(a.texto) == proibida
    ]


def _comando_negativo(item: ItemObjetivo) -> list[Violacao]:
    # Só o comando: no contexto, "não" é conteúdo. Asserção-razão tem comando fixo.
    if item.comando is None or item.formato is FormatoItem.ASSERCAO_RAZAO:
        return []
    encontrados = sorted(TERMOS_NEGATIVOS & _termos(item.comando))
    if not encontrados:
        return []
    return [
        Violacao(
            RegraQualidade.COMANDO_NEGATIVO,
            "comando",
            f"comando negativo ({', '.join(encontrados)}); use só para enfatizar o "
            "que não se deve fazer",
        )
    ]


def _contexto_curto_em(
    contexto: str | None, faixa: FaixaDificuldade | None
) -> list[Violacao]:
    if contexto is None or faixa is None:
        return []
    minimo = MINIMO_PALAVRAS_CONTEXTO.get(faixa)
    n = len(_palavras(contexto))
    if minimo is None or n >= minimo:
        return []
    return [
        Violacao(
            RegraQualidade.CONTEXTO_CURTO,
            "contexto",
            f"contexto com {n} palavras; a faixa {faixa.value} pede ao menos {minimo}",
        )
    ]


def _assercao_citacao(item: ItemObjetivo) -> list[Violacao]:
    if item.formato is not FormatoItem.ASSERCAO_RAZAO or item.assercoes is None:
        return []
    return [
        Violacao(
            RegraQualidade.ASSERCAO_CITACAO,
            alvo,
            "copia o trecho-base; o trecho sustenta, mas a redação é própria",
        )
        for alvo, texto in zip(("assercao", "razao"), item.assercoes, strict=False)
        if any(
            _semelhanca(texto, t) >= LIMIAR_ASSERCAO_CITACAO for t in item.trechos_base
        )
    ]


def _espacos(texto: str) -> str:
    return " ".join(texto.split())


def _formula_fora_do_trecho(item: ItemObjetivo) -> list[Violacao]:
    """R2 medido sem LLM: a fórmula copiada tem de estar num trecho enviado.
    Só registra: a fórmula pode estar no material com outra grafia."""
    if item.formula_citada is None or item.texto_dos_trechos is None:
        return []
    citada = _espacos(item.formula_citada)
    if any(citada in _espacos(t) for t in item.texto_dos_trechos):
        return []
    return [
        Violacao(
            RegraQualidade.FORMULA_FORA_DO_TRECHO,
            "formula_citada",
            f"“{citada}” não aparece em nenhum trecho enviado",
        )
    ]


def _variantes_do_numero(valor: float) -> set[str]:
    texto = f"{valor:g}"
    return {texto, texto.replace(".", ",")}


def _padrao_do_numero(numero: str, unidade: str) -> re.Pattern[str] | None:
    """Com unidade, o número só casa seguido do primeiro átomo dela ("2 etapas"
    não é "2 m"); sem unidade, só o decimal ou o de três dígitos ou mais: o
    inteiro pequeno ("2 etapas") não diverge de nada."""
    base = rf"(?<![\d.,]){re.escape(numero)}(?![\d]|[.,]\d)"
    atomo = re.match(r"[A-Za-zµΩ°]+", unidade.strip())
    if unidade.strip():
        if atomo is None:
            return None
        return re.compile(rf"{base}\s*{re.escape(atomo.group())}(?![A-Za-z])")
    forte = "." in numero or "," in numero or len(numero.lstrip("-")) >= 3
    return re.compile(base) if forte else None


def _numero_no_texto(item: ItemObjetivo) -> list[Violacao]:
    """O enunciado é montado dos dados: se o modelo repete um valor no texto, o
    texto pode divergir do que o sistema calculou. Só registra."""
    if item.dados_calculo is None:
        return []
    violacoes = []
    for alvo, texto in (("contexto", item.contexto), ("comando", item.comando)):
        if not texto:
            continue
        for simbolo, valor, unidade in item.dados_calculo:
            for numero in sorted(_variantes_do_numero(valor)):
                padrao = _padrao_do_numero(numero, unidade)
                if padrao is not None and padrao.search(texto):
                    violacoes.append(
                        Violacao(
                            RegraQualidade.NUMERO_NO_TEXTO,
                            alvo,
                            f"repete o valor de {simbolo} ({numero}); cite o símbolo",
                        )
                    )
                    break
    return violacoes


def _notacao(alvo: str, texto: str) -> list[Violacao]:
    """Não conserta: o crítico reemite, e o que sobrar aparece crua ao docente."""

    def _viol(detalhe: str) -> Violacao:
        return Violacao(RegraQualidade.NOTACAO_INVALIDA, alvo, detalhe)

    violacoes: list[Violacao] = []
    controle = next((c for c in texto if ord(c) < 0x20 and c != "\n"), None)
    if controle is not None:
        violacoes.append(
            _viol(
                f"caractere de controle U+{ord(controle):04X}: a barra do LaTeX "
                'precisa ir dobrada no JSON ("\\\\frac")'
            )
        )
    for segmento in separar(texto):
        if isinstance(segmento, Texto):
            if any(d in segmento.conteudo for d in ("\\(", "\\)", "\\[", "\\]")):
                violacoes.append(_viol("delimitador de fórmula sem par"))
            continue
        if "\n" in segmento.latex and not segmento.destaque:
            violacoes.append(
                _viol(
                    "quebra de linha dentro de \\(...\\): a barra do LaTeX foi "
                    "lida como \\n no JSON?"
                )
            )
        fora = comandos_fora_do_subconjunto(segmento.latex)
        if fora:
            violacoes.append(_viol(f"fora do subconjunto: {', '.join(fora)}"))
        elif para_mathml(segmento.latex) is None:
            violacoes.append(_viol(f"o conversor não aceita: {segmento.latex}"))
    return violacoes


def _contem_formula(texto: str) -> bool:
    return any(isinstance(s, Formula) for s in separar(texto))


def _notacao_objetiva(item: ItemObjetivo) -> list[Violacao]:
    # O enunciado montado já traz contexto, comando, afirmativas e asserção.
    alvos = _textos(item)
    if item.justificativa_correta is not None:
        alvos.append(("justificativa", item.justificativa_correta))
    if item.texto_verificacao_unicidade is not None:
        alvos.append(("verificacao", item.texto_verificacao_unicidade))
    alvos += [
        (f"invalidacao {letra}", motivo) for letra, motivo in item.invalidacoes or []
    ]
    return [v for alvo, texto in alvos for v in _notacao(alvo, texto)]


def validar_objetiva(item: ItemObjetivo) -> list[Violacao]:
    """Ordem determinística: a da tabela de regras, e dentro de cada
    regra, enunciado antes das alternativas, em ordem de letra. Nos formatos
    montados, as regras de alternativa não se aplicam: as
    alternativas são texto do sistema."""
    proposicao = item.formato is FormatoItem.PROPOSICAO
    return [
        *(_tamanho_alternativa(item) if proposicao else []),
        *(_correta_longa(item) if proposicao else []),
        *_termo_absoluto(item),
        *_mencao_fonte(item),
        *(_gemeos_insuficientes(item) if proposicao else []),
        *(_gemeo_na_correta(item) if proposicao else []),
        *(_invalidacao_letra_invalida(item) if proposicao else []),
        *_letra_citada_em_texto(item),
        *_alternativa_rotulo(item),
        *_alternativa_generica(item),
        *_pontuacao_incoerente(item),
        *_contexto_curto_em(item.contexto, item.faixa),
        *_comando_negativo(item),
        *_assercao_citacao(item),
        *_notacao_objetiva(item),
        *_formula_fora_do_trecho(item),
        *_numero_no_texto(item),
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


def _comandos(item: ItemDiscursivo) -> list[tuple[str, str]]:
    return (
        item.comandos if item.comandos is not None else [("enunciado", item.enunciado)]
    )


def _comando_ausente(item: ItemDiscursivo) -> list[Violacao]:
    return [
        Violacao(
            RegraQualidade.COMANDO_AUSENTE,
            alvo,
            "nenhum verbo de comando operacional (explique, compare, justifique…)",
        )
        for alvo, comando in _comandos(item)
        if not VERBOS_COMANDO & _termos(comando)
    ]


def _opiniao_pessoal(item: ItemDiscursivo) -> list[Violacao]:
    return [
        Violacao(
            RegraQualidade.OPINIAO_PESSOAL,
            alvo,
            f"pede opinião pessoal ({', '.join(termos)}); os aspectos esperados não a sustentam",
        )
        for alvo, comando in _comandos(item)
        if (termos := _frases(comando, TERMOS_OPINIAO))
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


def _alvos_discursiva(item: ItemDiscursivo) -> list[tuple[str, str]]:
    alvos = [("enunciado", item.enunciado)]
    # O contexto já está no enunciado montado: medir os dois duplicaria o achado.
    if item.contexto is not None and item.contexto not in item.enunciado:
        alvos.append(("contexto", item.contexto))
    if item.comandos is not None:
        alvos += item.comandos
    alvos += [(f"aspecto {i}", a.texto) for i, a in enumerate(item.aspectos, 1)]
    return alvos


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
        *_opiniao_pessoal(item),
        *_contexto_curto_em(item.contexto, item.faixa),
        *(v for alvo, texto in _alvos_discursiva(item) for v in _notacao(alvo, texto)),
    ]
