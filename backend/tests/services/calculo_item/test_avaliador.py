import pytest

from backend.app.domain import RegraQualidade
from backend.app.services.calculo_item.avaliador import (
    ErroCalculo,
    avaliar,
    em_unidade,
    quantidade,
)

Q = quantidade


def _valor(expressao, **dados):
    return avaliar(expressao, {k: Q(*v) for k, v in dados.items()})


def test_queda_livre():
    q = _valor("sqrt(2 * g * h)", g=(9.8, "m/s**2"), h=(5, "m"))
    assert em_unidade(q, "m/s") == pytest.approx(9.899, abs=1e-3)


def test_conversao_de_unidade():
    assert em_unidade(
        _valor("d / t", d=(36, "km"), t=(2, "h")), "m/s"
    ) == pytest.approx(5.0)


@pytest.mark.parametrize(
    "expressao",
    [
        "abs(-3) + exp(0) + ln(1) + log10(100) + sin(0) + cos(0) + tan(0) + pi * 0",
        "2 ** 3 - 1 / 4 + (-2)",
        "+3",
    ],
)
def test_nos_e_funcoes_aceitos(expressao):
    avaliar(expressao, {})


@pytest.mark.parametrize(
    "expressao",
    [
        "__import__('os').system('ls')",
        "x.real",
        "x[0]",
        "(lambda: 1)()",
        "[i for i in range(3)]",
        "x if x else 1",
        "'texto'",
        "True",
        "y + 1",  # símbolo não declarado
        "math.sqrt(4)",  # chamada por atributo
        "foo(2)",  # função fora da lista
        "1 < 2",
        "x @ x",
    ],
)
def test_recusa_no_fora_da_lista(expressao):
    with pytest.raises(ErroCalculo) as erro:
        avaliar(expressao, {"x": Q(1, "")})
    assert erro.value.regra is RegraQualidade.EXPRESSAO_INVALIDA


def test_recusa_nos_limites():
    # Parênteses não criam nó na AST: a profundidade vem de operador e chamada.
    aninhada = "abs(" * 40 + "1" + ")" * 40
    for expressao in [
        "1" + "+1" * 200,
        "-" * 40 + "1",
        aninhada,
        "2 ** 101",
        "10 ** 9 ** 9",
    ]:
        with pytest.raises(ErroCalculo) as erro:
            avaliar(expressao, {})
        assert erro.value.regra is RegraQualidade.EXPRESSAO_INVALIDA
    avaliar("2 ** 100", {})  # fronteira exata: aceita


def test_divisao_por_zero_e_nao_finito():
    for expressao in ["1 / 0", "ln(0)", "sqrt(-1)"]:
        with pytest.raises(ErroCalculo) as erro:
            avaliar(expressao, {})
        assert erro.value.regra is RegraQualidade.EXPRESSAO_INVALIDA


def test_somar_dimensoes_diferentes_e_incoerente():
    with pytest.raises(ErroCalculo) as erro:
        _valor("a + b", a=(1, "m"), b=(1, "s"))
    assert erro.value.regra is RegraQualidade.DIMENSAO_INCOERENTE


def test_resultado_nao_converte_para_a_unidade_pedida():
    q = _valor("a", a=(1, "m"))
    with pytest.raises(ErroCalculo) as erro:
        em_unidade(q, "s")
    assert erro.value.regra is RegraQualidade.DIMENSAO_INCOERENTE


def test_log_exige_argumento_sem_dimensao():
    with pytest.raises(ErroCalculo) as erro:
        _valor("log10(c)", c=(0.01, "mol/L"))
    assert erro.value.regra is RegraQualidade.DIMENSAO_INCOERENTE
    ph = _valor(
        "-log10(c / (1 mol/L))".replace("(1 mol/L)", "c0"),
        c=(0.01, "mol/L"),
        c0=(1, "mol/L"),
    )
    assert em_unidade(ph, "dimensionless") == pytest.approx(2.0)


def test_seno_em_graus_e_em_radianos():
    graus = avaliar("sin(a)", {"a": Q(30, "degree")})
    radianos = avaliar("sin(a)", {"a": Q(0.5235987755982988, "radian")})
    assert em_unidade(graus, "dimensionless") == pytest.approx(0.5)
    assert em_unidade(radianos, "dimensionless") == pytest.approx(0.5)


def test_seno_de_comprimento_e_incoerente():
    with pytest.raises(ErroCalculo):
        _valor("sin(h)", h=(1, "m"))


@pytest.mark.parametrize("nome", ["sqrt", "pi", "ln", "1x", "x y", "é", ""])
def test_simbolo_invalido(nome):
    from backend.app.services.calculo_item.avaliador import SIMBOLO_VALIDO

    assert not SIMBOLO_VALIDO(nome)


def test_unidade_desconhecida():
    with pytest.raises(ErroCalculo) as erro:
        Q(1, "furlongs_por_quinzena_xyz")
    assert erro.value.regra is RegraQualidade.DIMENSAO_INCOERENTE


def test_unidade_logaritmica_composta_vira_violacao_e_nao_500():
    """pint 0.25: converter para "dB/km" levanta AssertionError, não PintError
    (atenuação de enlace, medido numa geração real de telecom)."""
    with pytest.raises(ErroCalculo) as erro:
        em_unidade(_valor("a", a=(3, "m")), "dB/km")
    assert erro.value.regra is RegraQualidade.DIMENSAO_INCOERENTE


def test_conta_com_dado_em_db_por_km_vira_violacao():
    with pytest.raises(ErroCalculo) as erro:
        em_unidade(_valor("a * d", a=(0.2, "dB/km"), d=(10, "km")), "dB")
    assert erro.value.regra is RegraQualidade.DIMENSAO_INCOERENTE
