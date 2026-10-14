"""Montagem da questão de cálculo — Núcleo Determinístico.

`calcular` é a única função que produz valor, e serve à geração e à
reverificação da auditoria: a estrutura gravada reproduz as alternativas sem
LLM."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.domain import FormatoItem, RegraQualidade
from backend.app.schemas.geracao import LETRAS
from backend.app.services.calculo_item.avaliador import (
    SIMBOLO_VALIDO,
    ErroCalculo,
    avaliar,
    em_unidade,
    quantidade,
)
from backend.app.services.calculo_item.formatacao import (
    formatar_valor,
    unidade_latex,
    valor_com_unidade,
)
from backend.app.services.calculo_item.latex import resolucao_latex, simbolo_latex
from backend.app.services.geracao.formatos import (
    AlternativaMontada,
    InvalidacaoMontada,
    QuestaoMontada,
    _embaralhar,
    juntar,
)
from backend.app.services.qualidade.validador_itens import Violacao

ALGARISMOS_DADO = 6


class CalculoNaoMontavel(Exception):
    def __init__(self, violacoes: list[Violacao]):
        super().__init__("; ".join(f"{v.alvo}: {v.detalhe}" for v in violacoes))
        self.violacoes = violacoes


@dataclass(frozen=True)
class Valor:
    numero: float
    formatado: str
    alternativa: str  # \( valor unidade \)


@dataclass(frozen=True)
class Calculado:
    correta: Valor
    erros: list[Valor]
    linhas_de_dados: list[str]
    resolucao: str


def _arredondar(x: float) -> float:
    return float(f"{x:.{ALGARISMOS_DADO - 1}e}")


def calcular(estrutura: dict) -> Calculado:
    """`estrutura`: dados, expressao, unidade_resultado, erros. Levanta
    `CalculoNaoMontavel` com TODAS as violações encontradas, não só a primeira."""
    violacoes: list[Violacao] = []
    grandezas = {}
    linhas: list[str] = []
    valores_fmt: dict[str, str] = {}
    for dado in estrutura["dados"]:
        simbolo = dado["simbolo"]
        alvo = f"dado {simbolo}"
        if not SIMBOLO_VALIDO(simbolo):
            violacoes.append(
                Violacao(
                    RegraQualidade.EXPRESSAO_INVALIDA,
                    alvo,
                    "símbolo inválido: use letras, dígitos e _, sem nome de função nem de constante",
                )
            )
            continue
        try:
            valor = _arredondar(float(dado["valor"]))
            grandezas[simbolo] = quantidade(valor, dado["unidade"])
        except ErroCalculo as exc:
            violacoes.append(Violacao(exc.regra, alvo, exc.detalhe))
            continue
        unidade_ltx = unidade_latex(dado["unidade"])
        if unidade_ltx is None:
            violacoes.append(
                Violacao(
                    RegraQualidade.DIMENSAO_INCOERENTE,
                    alvo,
                    f"unidade sem representação: {dado['unidade']}",
                )
            )
            continue
        fmt = formatar_valor(valor, ALGARISMOS_DADO, aparar=True)
        valores_fmt[simbolo] = fmt
        linhas.append(
            f"\\({simbolo_latex(simbolo)} = {valor_com_unidade(fmt, unidade_ltx)}\\)"
        )

    unidade_res = estrutura["unidade_resultado"]
    unidade_res_ltx = unidade_latex(unidade_res)
    if unidade_res_ltx is None:
        violacoes.append(
            Violacao(
                RegraQualidade.DIMENSAO_INCOERENTE,
                "unidade_resultado",
                f"unidade sem representação: {unidade_res}",
            )
        )

    def _valor(expressao: str, alvo: str) -> Valor | None:
        try:
            numero = em_unidade(avaliar(expressao, grandezas), unidade_res)
        except ErroCalculo as exc:
            violacoes.append(Violacao(exc.regra, alvo, exc.detalhe))
            return None
        fmt = formatar_valor(numero)
        return Valor(
            numero, fmt, f"\\({valor_com_unidade(fmt, unidade_res_ltx or '')}\\)"
        )

    correta = _valor(estrutura["expressao"], "expressao")
    erros = [
        _valor(e["expressao"], f"erro {i}")
        for i, e in enumerate(estrutura["erros"], start=1)
    ]
    if violacoes or correta is None or any(e is None for e in erros):
        raise CalculoNaoMontavel(violacoes)

    vistos: dict[str, str] = {correta.formatado: "a correta"}
    for i, erro in enumerate(erros, start=1):
        if erro.formatado in vistos:
            violacoes.append(
                Violacao(
                    RegraQualidade.DISTRATORES_COINCIDENTES,
                    f"erro {i}",
                    f"o erro {i} dá {erro.formatado}, igual a {vistos[erro.formatado]}",
                )
            )
        else:
            vistos[erro.formatado] = f"o erro {i}"
    if violacoes:
        raise CalculoNaoMontavel(violacoes)

    resolucao = resolucao_latex(
        estrutura["expressao"],
        valores_fmt,
        unidade_res_ltx or "",
        correta.formatado,
        None,
    )
    return Calculado(correta, erros, linhas, f"\\({resolucao}\\)")


def montar_calculo(saida, k: int, numero: int) -> QuestaoMontada:
    dados = []
    for d in saida.dados:
        try:
            valor = _arredondar(float(d.valor))
        except TypeError, ValueError:
            valor = d.valor
        dados.append({"simbolo": d.simbolo, "valor": valor, "unidade": d.unidade})
    estrutura = {
        "contexto": saida.contexto,
        "dados": dados,
        "expressao": saida.expressao,
        "unidade_resultado": saida.unidade_resultado,
        "formula_citada": saida.formula_citada,
        "erros": [
            {"descricao": e.descricao, "expressao": e.expressao} for e in saida.erros
        ],
    }
    calculado = calcular(estrutura)

    candidatos = [
        (calculado.correta, None),
        *zip(calculado.erros, saida.erros, strict=True),
    ]
    ordem = _embaralhar(candidatos, numero)
    letra_correta = LETRAS[next(i for i, (_, e) in enumerate(ordem) if e is None)]
    pergunta = juntar(saida.comando, "Dados:\n" + "\n".join(calculado.linhas_de_dados))
    return QuestaoMontada(
        formato=FormatoItem.CALCULO,
        contexto=saida.contexto,
        comando=saida.comando,
        pergunta=pergunta,
        enunciado=juntar(saida.contexto, pergunta),
        nivel_bloom=saida.nivel_bloom,
        tema=saida.tema,
        subtema=saida.subtema,
        alternativas=[AlternativaMontada(v.alternativa, False) for v, _ in ordem],
        letra_correta=letra_correta,
        fontes=list(saida.fontes),
        objetivo_cognitivo=saida.objetivo_cognitivo,
        justificativa_correta=calculado.resolucao,
        invalidacoes=[
            InvalidacaoMontada(
                LETRAS[i], f"{erro.descricao} — leva a {valor.formatado}"
            )
            for i, (valor, erro) in enumerate(ordem)
            if erro is not None
        ],
        verificacao_unicidade=True,
        texto_verificacao_unicidade=(
            "Por construção, os valores das alternativas são distintos depois do "
            "arredondamento, e só a expressão do enunciado leva ao da correta."
        ),
        estrutura_formato=estrutura,
    )
