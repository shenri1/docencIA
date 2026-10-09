"""Formato de item e itens da discursiva — Núcleo Determinístico, nunca chama LLM.

A atribuição é função pura de (faixa, posição, K): é isso que dá o mesmo
formato ao mesmo número na retomada em lotes. A montagem (Tasks 5 e 6) pega a
saída do modelo e monta o que pode ser montado sem LLM — enunciado,
alternativas, correta, gêmeos e invalidações dos formatos montados.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from itertools import product

from backend.app.domain import FaixaDificuldade, FormatoItem
from backend.app.schemas.geracao import CAMPOS_AFIRMATIVA, LETRAS, n_afirmativas

# Ordem da tabela: é a ordem do rodízio.
_FORMATOS_POR_FAIXA = {
    FaixaDificuldade.FACIL: (FormatoItem.PROPOSICAO,),
    FaixaDificuldade.MEDIA: (FormatoItem.PROPOSICAO, FormatoItem.AFIRMATIVAS),
    FaixaDificuldade.DIFICIL: (
        FormatoItem.PROPOSICAO,
        FormatoItem.AFIRMATIVAS,
        FormatoItem.ASSERCAO_RAZAO,
    ),
}

# Ordem do rodízio da asserção-razão. Começa longe do "ambas verdadeiras e a II
# justifica a I", que é para onde o modelo tende quando escolhe sozinho.
CONFIGURACOES_ASSERCAO = ("vv_nao_justifica", "vf", "fv", "vv_justifica", "ff")


def _cabe(formato: FormatoItem, k: int) -> bool:
    if formato is FormatoItem.AFIRMATIVAS:
        return k >= 4
    if formato is FormatoItem.ASSERCAO_RAZAO:
        return k == 5
    return True


def atribuir_formato(
    faixa: FaixaDificuldade, posicao_na_faixa: int, k: int
) -> FormatoItem:
    formatos = [f for f in _FORMATOS_POR_FAIXA[faixa] if _cabe(f, k)]
    return formatos[posicao_na_faixa % len(formatos)]


def configuracoes_afirmativas(n: int) -> list[tuple[bool, ...]]:
    """Subconjuntos verdadeiros não vazios, alternando o tamanho (2, 1, 3, 4…)
    para o gabarito não ficar previsível. "Nenhuma verdadeira" não existe."""
    por_tamanho: dict[int, list[tuple[bool, ...]]] = {}
    for combinacao in product((True, False), repeat=n):
        if any(combinacao):
            por_tamanho.setdefault(sum(combinacao), []).append(combinacao)
    filas = [por_tamanho[t] for t in sorted(por_tamanho, key=lambda t: (t != 2, t))]
    resultado: list[tuple[bool, ...]] = []
    for i in range(max(len(f) for f in filas)):
        resultado.extend(fila[i] for fila in filas if i < len(fila))
    return resultado


def atribuir_configuracao(
    formato: FormatoItem, ordinal_no_formato: int, k: int
) -> tuple[bool, ...] | str | None:
    if formato is FormatoItem.AFIRMATIVAS:
        opcoes = configuracoes_afirmativas(n_afirmativas(k))
    elif formato is FormatoItem.ASSERCAO_RAZAO:
        opcoes = list(CONFIGURACOES_ASSERCAO)
    else:
        return None
    return opcoes[ordinal_no_formato % len(opcoes)]


def atribuir_n_itens(faixa: FaixaDificuldade, ordinal_na_faixa: int) -> int | None:
    """Só a discursiva difícil tem itens: ela já é estudo de caso."""
    if faixa is not FaixaDificuldade.DIFICIL:
        return None
    return 2 if ordinal_na_faixa % 2 == 0 else 3


_CONTEXTUALIZACAO = {
    FaixaDificuldade.FACIL: (
        "Contextualização: nenhuma exigida. Pergunta direta é permitida, e o campo "
        "contexto pode ficar vazio."
    ),
    FaixaDificuldade.MEDIA: (
        "Contextualização: aplicação. Escreva no campo contexto uma situação curta, "
        "de 1 a 2 frases, em que o conceito é usado, e faça o comando remeter a ela."
    ),
    FaixaDificuldade.DIFICIL: (
        "Contextualização: cenário. Escreva no campo contexto uma situação-problema "
        "com dados a interpretar; o comando pede uma decisão, um diagnóstico ou uma "
        "conclusão sobre ela. Todo conhecimento necessário para responder vem dos "
        "trechos."
    ),
}


def texto_contextualizacao(faixa: FaixaDificuldade) -> str:
    return _CONTEXTUALIZACAO[faixa]


def juntar(*partes: str) -> str:
    """Partes em branco somem: na fácil, o contexto vazio não deixa linha em
    branco no começo do enunciado. O texto das partes não é alterado."""
    return "\n\n".join(p for p in partes if p.strip())


@dataclass(frozen=True)
class AlternativaMontada:
    texto: str
    e_gemeo_malvado: bool


@dataclass(frozen=True)
class InvalidacaoMontada:
    letra: str
    motivo: str


@dataclass(frozen=True)
class QuestaoMontada:
    """A forma que validador, persistência e gabarito leem, venha do modelo
    (proposição) ou do sistema (formatos montados)."""

    formato: FormatoItem
    contexto: str
    comando: str
    # O enunciado sem o contexto: é o que a substituição compara.
    pergunta: str
    enunciado: str
    nivel_bloom: str
    tema: str
    subtema: str
    alternativas: list[AlternativaMontada]
    letra_correta: str
    fontes: list
    objetivo_cognitivo: str
    justificativa_correta: str
    invalidacoes: list[InvalidacaoMontada]
    verificacao_unicidade: bool
    texto_verificacao_unicidade: str
    estrutura_formato: dict
    assercoes: list[str] | None = None


@dataclass(frozen=True)
class AspectoMontado:
    texto: str
    fonte: object
    item: int | None


@dataclass(frozen=True)
class DiscursivaMontada:
    contexto: str
    comandos: list[str]
    pergunta: str
    enunciado: str
    nivel_bloom: str
    tema: str
    subtema: str
    objetivo_cognitivo: str
    aspectos: list[AspectoMontado]
    n_itens: int | None


def montar_proposicao(saida) -> QuestaoMontada:
    j = saida.justificativa
    return QuestaoMontada(
        formato=FormatoItem.PROPOSICAO,
        contexto=saida.contexto,
        comando=saida.comando,
        pergunta=saida.comando,
        enunciado=juntar(saida.contexto, saida.comando),
        nivel_bloom=saida.nivel_bloom,
        tema=saida.tema,
        subtema=saida.subtema,
        alternativas=[
            AlternativaMontada(a.texto, a.e_gemeo_malvado) for a in saida.alternativas
        ],
        letra_correta=saida.letra_correta,
        fontes=list(saida.fontes),
        objetivo_cognitivo=j.objetivo_cognitivo,
        justificativa_correta=j.justificativa_correta,
        invalidacoes=[
            InvalidacaoMontada(i.letra, i.motivo) for i in j.invalidacao_distratores
        ],
        verificacao_unicidade=j.verificacao_unicidade,
        texto_verificacao_unicidade=j.texto_verificacao_unicidade,
        estrutura_formato={"contexto": saida.contexto},
    )


ROMANOS = ("I", "II", "III", "IV")
LETRAS_ITEM = "abc"
FECHO_AFIRMATIVAS = "É correto o que se afirma em"
ABERTURA_ASSERCAO = (
    "Considerando as informações apresentadas, avalie as asserções a seguir e a "
    "relação proposta entre elas."
)
FECHO_ASSERCAO = "A respeito dessas asserções, assinale a opção correta."
ABERTURA_ITENS = (
    "A partir das informações apresentadas, faça o que se pede nos itens a seguir."
)
# Os 5 textos clássicos, fixos em código. A ordem do dicionário é a ordem antes do
# embaralhamento.
TEXTO_ASSERCAO = {
    "vv_justifica": "As asserções I e II são proposições verdadeiras, e a II é uma "
    "justificativa correta da I.",
    "vv_nao_justifica": "As asserções I e II são proposições verdadeiras, mas a II "
    "não é uma justificativa correta da I.",
    "vf": "A asserção I é uma proposição verdadeira, e a II é uma proposição falsa.",
    "fv": "A asserção I é uma proposição falsa, e a II é uma proposição verdadeira.",
    "ff": "As asserções I e II são proposições falsas.",
}
# (I verdadeira, II verdadeira, II justifica I).
_JULGAMENTO_ASSERCAO = {
    "vv_justifica": (True, True, True),
    "vv_nao_justifica": (True, True, False),
    "vf": (True, False, False),
    "fv": (False, True, False),
    "ff": (False, False, False),
}


def _vf(valor: bool) -> str:
    return "verdadeira" if valor else "falsa"


def _lista(nomes: list[str]) -> str:
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


def rotulo_combinacao(combinacao: tuple[bool, ...]) -> str:
    nomes = _lista([ROMANOS[i] for i, v in enumerate(combinacao) if v])
    return f"{nomes}." if all(combinacao) else f"{nomes}, apenas."


def _embaralhar(itens: list, numero: int) -> list:
    """Semente derivada do número da questão: a mesma questão sai sempre com a
    correta na mesma posição."""
    ordem = list(itens)
    random.Random(numero).shuffle(ordem)
    return ordem


def _distancia(a: tuple[bool, ...], b: tuple[bool, ...]) -> int:
    return sum(x != y for x, y in zip(a, b, strict=True))


def _motivo_afirmativas(combinacao, julgamento, afirmativas) -> str:
    j = next(i for i, (x, y) in enumerate(zip(combinacao, julgamento, strict=True)) if x != y)
    if afirmativas[j].verdadeira:
        return (
            f"Deixa de fora a afirmativa {ROMANOS[j]}, que é verdadeira: "
            f"{afirmativas[j].justificativa}"
        )
    return (
        f"Inclui a afirmativa {ROMANOS[j]}, que é falsa: {afirmativas[j].justificativa}"
    )


def montar_afirmativas(saida, configuracao: tuple[bool, ...], k: int, numero: int) -> QuestaoMontada:
    afirmativas = [getattr(saida, nome) for nome in CAMPOS_AFIRMATIVA[: len(configuracao)]]
    julgamento = tuple(a.verdadeira for a in afirmativas)
    if julgamento != tuple(configuracao):
        # O schema impõe a configuração como Literal: divergir é bug, não modelo.
        raise ValueError(f"julgamento {julgamento} difere da configuração {configuracao}")
    outras = [
        c for c in product((True, False), repeat=len(julgamento))
        if any(c) and c != julgamento
    ]
    # Estável: dentro da mesma distância, fica a ordem canônica do product.
    distratores = sorted(outras, key=lambda c: _distancia(c, julgamento))[: k - 1]
    ordem = _embaralhar([julgamento, *distratores], numero)
    linhas = "\n".join(f"{ROMANOS[i]}. {a.texto}" for i, a in enumerate(afirmativas))
    pergunta = juntar(saida.comando, linhas, FECHO_AFIRMATIVAS)
    return QuestaoMontada(
        formato=FormatoItem.AFIRMATIVAS,
        contexto=saida.contexto,
        comando=saida.comando,
        pergunta=pergunta,
        enunciado=juntar(saida.contexto, pergunta),
        nivel_bloom=saida.nivel_bloom,
        tema=saida.tema,
        subtema=saida.subtema,
        alternativas=[
            AlternativaMontada(
                rotulo_combinacao(c), c != julgamento and _distancia(c, julgamento) == 1
            )
            for c in ordem
        ],
        letra_correta=LETRAS[ordem.index(julgamento)],
        fontes=list(saida.fontes),
        objetivo_cognitivo=saida.objetivo_cognitivo,
        justificativa_correta="\n".join(
            f"{ROMANOS[i]} é {_vf(a.verdadeira)}: {a.justificativa}"
            for i, a in enumerate(afirmativas)
        ),
        invalidacoes=[
            InvalidacaoMontada(LETRAS[i], _motivo_afirmativas(c, julgamento, afirmativas))
            for i, c in enumerate(ordem)
            if c != julgamento
        ],
        verificacao_unicidade=True,
        texto_verificacao_unicidade=(
            f"Por construção, “{rotulo_combinacao(julgamento)}” é a única combinação "
            "compatível com o julgamento das afirmativas."
        ),
        estrutura_formato={
            "contexto": saida.contexto,
            "afirmativas": [
                {"texto": a.texto, "verdadeira": a.verdadeira, "justificativa": a.justificativa}
                for a in afirmativas
            ],
        },
    )


def _distancia_assercao(a: str, b: str) -> int:
    ja, jb = _JULGAMENTO_ASSERCAO[a], _JULGAMENTO_ASSERCAO[b]
    d = (ja[0] != jb[0]) + (ja[1] != jb[1])
    if ja[0] and ja[1] and jb[0] and jb[1]:
        d += ja[2] != jb[2]
    return d


def _motivo_assercao(alternativa: str, correta: str, saida) -> str:
    ja, jc = _JULGAMENTO_ASSERCAO[alternativa], _JULGAMENTO_ASSERCAO[correta]
    if ja[0] != jc[0]:
        return f"A asserção I é {_vf(jc[0])}: {saida.justificativa_assercao}"
    if ja[1] != jc[1]:
        return f"A asserção II é {_vf(jc[1])}: {saida.justificativa_razao}"
    relacao = "é" if jc[2] else "não é"
    return f"A II {relacao} uma justificativa correta da I: {saida.justificativa_razao}"


def montar_assercao_razao(saida, configuracao: str, numero: int) -> QuestaoMontada:
    ordem = _embaralhar(list(TEXTO_ASSERCAO), numero)
    julgamento = _JULGAMENTO_ASSERCAO[configuracao]
    justificativa = (
        f"I é {_vf(julgamento[0])}: {saida.justificativa_assercao}\n"
        f"II é {_vf(julgamento[1])}: {saida.justificativa_razao}"
    )
    if julgamento[0] and julgamento[1]:
        justificativa += f"\nA II {'é' if julgamento[2] else 'não é'} uma justificativa correta da I."
    pergunta = juntar(
        ABERTURA_ASSERCAO, f"I. {saida.assercao}", "PORQUE", f"II. {saida.razao}", FECHO_ASSERCAO
    )
    return QuestaoMontada(
        formato=FormatoItem.ASSERCAO_RAZAO,
        contexto=saida.contexto,
        comando=ABERTURA_ASSERCAO,
        pergunta=pergunta,
        enunciado=juntar(saida.contexto, pergunta),
        nivel_bloom=saida.nivel_bloom,
        tema=saida.tema,
        subtema=saida.subtema,
        alternativas=[
            AlternativaMontada(
                TEXTO_ASSERCAO[c],
                c != configuracao and _distancia_assercao(c, configuracao) == 1,
            )
            for c in ordem
        ],
        letra_correta=LETRAS[ordem.index(configuracao)],
        fontes=list(saida.fontes),
        objetivo_cognitivo=saida.objetivo_cognitivo,
        justificativa_correta=justificativa,
        invalidacoes=[
            InvalidacaoMontada(LETRAS[i], _motivo_assercao(c, configuracao, saida))
            for i, c in enumerate(ordem)
            if c != configuracao
        ],
        verificacao_unicidade=True,
        texto_verificacao_unicidade=(
            "Por construção, só uma das cinco alternativas clássicas corresponde ao "
            "julgamento das duas proposições."
        ),
        estrutura_formato={
            "contexto": saida.contexto,
            "assercao": saida.assercao,
            "razao": saida.razao,
            "justificativa_assercao": saida.justificativa_assercao,
            "justificativa_razao": saida.justificativa_razao,
            "configuracao": configuracao,
        },
        assercoes=[saida.assercao, saida.razao],
    )


def montar_objetiva(saida, formato: FormatoItem, configuracao, k: int, numero: int) -> QuestaoMontada:
    if formato is FormatoItem.AFIRMATIVAS:
        return montar_afirmativas(saida, configuracao, k, numero)
    if formato is FormatoItem.ASSERCAO_RAZAO:
        return montar_assercao_razao(saida, configuracao, numero)
    return montar_proposicao(saida)


def montar_discursiva(saida) -> DiscursivaMontada:
    if not hasattr(saida, "itens"):
        return DiscursivaMontada(
            contexto=saida.contexto,
            comandos=[saida.comando],
            pergunta=saida.comando,
            enunciado=juntar(saida.contexto, saida.comando),
            nivel_bloom=saida.nivel_bloom,
            tema=saida.tema,
            subtema=saida.subtema,
            objetivo_cognitivo=saida.objetivo_cognitivo,
            aspectos=[
                AspectoMontado(a.texto, a.fonte, None) for a in saida.aspectos_esperados
            ],
            n_itens=None,
        )
    comandos = [item.comando for item in saida.itens]
    linhas = "\n".join(f"{LETRAS_ITEM[i]}) {c}" for i, c in enumerate(comandos))
    pergunta = juntar(ABERTURA_ITENS, linhas)
    return DiscursivaMontada(
        contexto=saida.contexto,
        comandos=comandos,
        pergunta=pergunta,
        enunciado=juntar(saida.contexto, pergunta),
        nivel_bloom=saida.nivel_bloom,
        tema=saida.tema,
        subtema=saida.subtema,
        objetivo_cognitivo=saida.objetivo_cognitivo,
        aspectos=[
            AspectoMontado(a.texto, a.fonte, i + 1)
            for i, item in enumerate(saida.itens)
            for a in item.aspectos_esperados
        ],
        n_itens=len(comandos),
    )


_PEDIDO_ASSERCAO = {
    "vv_justifica": "a asserção I e a razão II devem ser verdadeiras, e a II deve ser "
    "uma justificativa correta da I",
    "vv_nao_justifica": "a asserção I e a razão II devem ser verdadeiras, mas a II não "
    "pode ser uma justificativa correta da I",
    "vf": "a asserção I deve ser verdadeira, e a razão II, falsa",
    "fv": "a asserção I deve ser falsa, e a razão II, verdadeira",
    "ff": "a asserção I e a razão II devem ser falsas",
}


def _frase_afirmativas(nomes: list[str], valor: bool) -> str:
    if len(nomes) == 1:
        return f"a afirmativa {nomes[0]} deve ser {_vf(valor)}"
    return f"as afirmativas {_lista(nomes)} devem ser {_vf(valor)}s"


def texto_pedido_formato(formato: FormatoItem, configuracao, k: int) -> str:
    if formato is FormatoItem.AFIRMATIVAS:
        verdadeiras = [ROMANOS[i] for i, v in enumerate(configuracao) if v]
        falsas = [ROMANOS[i] for i, v in enumerate(configuracao) if not v]
        partes = [_frase_afirmativas(verdadeiras, True)]
        if falsas:
            partes.append(_frase_afirmativas(falsas, False))
        return (
            f"Formato: análise de {len(configuracao)} afirmativas sobre um único "
            f"conteúdo. Nesta questão, {'; '.join(partes)}. O sistema monta as "
            "alternativas."
        )
    if formato is FormatoItem.ASSERCAO_RAZAO:
        return (
            f"Formato: asserção-razão. Nesta questão, {_PEDIDO_ASSERCAO[configuracao]}. "
            "O sistema monta o comando e as alternativas."
        )
    return f"Formato: proposição, com exatamente {k} alternativas."


def texto_pedido_itens(n_itens: int) -> str:
    return (
        f"Divida a questão em {n_itens} itens (a a {LETRAS_ITEM[n_itens - 1]}) sobre o "
        "mesmo contexto, cada um com o seu comando e de 1 a 3 aspectos esperados, cada "
        "aspecto com a sua fonte. Nenhum item depende da resposta de outro."
    )
