from types import SimpleNamespace

import pytest

from backend.app.domain import FormatoItem, RegraQualidade
from backend.app.services.calculo_item.montagem import (
    CalculoNaoMontavel,
    calcular,
    montar_calculo,
)


def _saida(**mudancas):
    base = dict(  # noqa: C408
        contexto="Um objeto é solto de uma altura h.",
        comando="Qual a velocidade v ao chegar ao solo?",
        dados=[
            SimpleNamespace(simbolo="g", valor=9.8, unidade="m/s**2"),
            SimpleNamespace(simbolo="h", valor=5.0, unidade="m"),
        ],
        formula_citada="v = sqrt(2 g h)",
        expressao="sqrt(2 * g * h)",
        unidade_resultado="m/s",
        erros=[
            SimpleNamespace(descricao="esquece o fator 2", expressao="sqrt(g * h)"),
            SimpleNamespace(descricao="divide por 2", expressao="sqrt(2 * g * h) / 2"),
            SimpleNamespace(
                descricao="multiplica por 2", expressao="sqrt(2 * g * h) * 2"
            ),
        ],
        objetivo_cognitivo="aplicar",
        fontes=[
            SimpleNamespace(
                identificador_material="P1",
                localizacao="p. 1",
                trecho_base="v = sqrt(2gh)",
            )
        ],
        tema="queda livre",
        subtema="velocidade",
        nivel_bloom="aplicar",
    )
    base.update(mudancas)
    return SimpleNamespace(**base)


def test_monta_questao_de_calculo():
    montada = montar_calculo(_saida(), k=4, numero=7)
    assert montada.formato is FormatoItem.CALCULO
    assert len(montada.alternativas) == 4
    assert (
        montada.alternativas[ord(montada.letra_correta) - 65].texto
        == r"\(9{,}90\ \frac{\mathrm{m}}{\mathrm{s}}\)"
    )
    assert all(not a.e_gemeo_malvado for a in montada.alternativas)
    assert len(montada.invalidacoes) == 3
    assert all("leva a" in i.motivo for i in montada.invalidacoes)
    assert montada.verificacao_unicidade is True
    assert r"\sqrt{2 \cdot 9{,}8 \cdot 5}" in montada.justificativa_correta


def test_enunciado_tem_bloco_de_dados_do_sistema():
    montada = montar_calculo(_saida(), k=4, numero=7)
    assert montada.enunciado.startswith("Um objeto é solto de uma altura h.")
    assert "Dados:" in montada.enunciado
    assert r"\(g = 9{,}8\ \frac{\mathrm{m}}{\mathrm{s}^{2}}\)" in montada.enunciado
    assert montada.pergunta == montada.enunciado.removeprefix(montada.contexto + "\n\n")


def test_posicao_da_correta_e_deterministica():
    a = montar_calculo(_saida(), k=4, numero=7)
    b = montar_calculo(_saida(), k=4, numero=7)
    assert a.letra_correta == b.letra_correta and a.alternativas == b.alternativas


def test_estrutura_reproduz_sem_llm():
    montada = montar_calculo(_saida(), k=4, numero=7)
    calculado = calcular(montada.estrutura_formato)
    textos = {a.texto for a in montada.alternativas}
    assert {
        calculado.correta.alternativa,
        *(e.alternativa for e in calculado.erros),
    } == textos


def test_dados_sao_calculados_arredondados():
    saida = _saida(
        dados=[
            SimpleNamespace(simbolo="g", valor=9.8123456789, unidade="m/s**2"),
            SimpleNamespace(simbolo="h", valor=5.0, unidade="m"),
        ]
    )
    montada = montar_calculo(saida, k=4, numero=1)
    assert montada.estrutura_formato["dados"][0]["valor"] == 9.81235


def test_distratores_coincidentes_depois_do_arredondamento():
    saida = _saida(
        erros=[
            SimpleNamespace(descricao="a", expressao="sqrt(2 * g * h) * 1.0004"),
            SimpleNamespace(descricao="b", expressao="sqrt(g * h)"),
            SimpleNamespace(descricao="c", expressao="sqrt(2 * g * h) / 2"),
        ]
    )
    with pytest.raises(CalculoNaoMontavel) as erro:
        montar_calculo(saida, k=4, numero=1)
    regras = [v.regra for v in erro.value.violacoes]
    assert RegraQualidade.DISTRATORES_COINCIDENTES in regras


def test_expressao_invalida_nao_impede_ver_as_outras_violacoes():
    saida = _saida(
        expressao="__import__('os')",
        erros=[
            SimpleNamespace(descricao="a", expressao="sqrt(g * h)"),
            SimpleNamespace(descricao="b", expressao="g + h"),  # m/s² + m
            SimpleNamespace(descricao="c", expressao="h"),
        ],
    )
    with pytest.raises(CalculoNaoMontavel) as erro:
        montar_calculo(saida, k=4, numero=1)
    por_alvo = {v.alvo: v.regra for v in erro.value.violacoes}
    assert por_alvo["expressao"] is RegraQualidade.EXPRESSAO_INVALIDA
    assert por_alvo["erro 2"] is RegraQualidade.DIMENSAO_INCOERENTE


def test_simbolo_invalido():
    saida = _saida(dados=[SimpleNamespace(simbolo="sqrt", valor=1.0, unidade="")])
    with pytest.raises(CalculoNaoMontavel) as erro:
        montar_calculo(saida, k=4, numero=1)
    assert erro.value.violacoes[0].alvo == "dado sqrt"


def test_erro_igual_a_correta_coincide():
    saida = _saida(
        erros=[
            SimpleNamespace(descricao="a", expressao="sqrt(2 * g * h)"),
            SimpleNamespace(descricao="b", expressao="sqrt(g * h)"),
            SimpleNamespace(descricao="c", expressao="sqrt(2 * g * h) / 2"),
        ]
    )
    with pytest.raises(CalculoNaoMontavel) as erro:
        montar_calculo(saida, k=4, numero=1)
    assert [v.alvo for v in erro.value.violacoes] == ["erro 1"]
    assert erro.value.violacoes[0].regra is RegraQualidade.DISTRATORES_COINCIDENTES
