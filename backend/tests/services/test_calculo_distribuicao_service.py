import pytest

from backend.app.domain import FaixaDificuldade
from backend.app.exceptions import ParametrosInconsistentesException
from backend.app.services.calculo_distribuicao_service import (
    DistribuicaoQuestoes,
    calcular_distribuicao,
)


def test_sem_resto_distribui_exatamente_os_percentuais():
    """"""
    d = calcular_distribuicao(50, 10, 60, 30)
    assert (d.faceis, d.medias, d.dificeis) == (5, 30, 15)


def test_resto_um_vai_para_o_maior_fracionario():
    """Segundo caso do material de referência: pisos 4/28/14, sobra 1 unidade,
    e o fracionário de fácil (70) é o maior."""
    d = calcular_distribuicao(47, 10, 60, 30)
    assert (d.faceis, d.medias, d.dificeis) == (5, 28, 14)


def test_empate_entre_facil_e_media_vai_para_media():
    """Fracionários 50/50/0: fácil e média empatam, média vence por D > M > F."""
    d = calcular_distribuicao(2, 25, 25, 50)
    assert (d.faceis, d.medias, d.dificeis) == (0, 1, 1)


def test_resto_dois_com_empate_na_segunda_unidade():
    """O caso mais completo: fracionários 57/57/86. Difícil leva a primeira
    unidade por ter o maior; fácil e média empatam em 57 e média vence."""
    d = calcular_distribuicao(29, 33, 33, 34)
    assert (d.faceis, d.medias, d.dificeis) == (9, 10, 10)


def test_resto_um_sem_empate():
    d = calcular_distribuicao(29, 25, 50, 25)
    assert (d.faceis, d.medias, d.dificeis) == (7, 15, 7)


def test_desempate_triplo():
    d = calcular_distribuicao(3, 33, 33, 34)
    assert (d.faceis, d.medias, d.dificeis) == (1, 1, 1)


def test_banco_de_uma_questao():
    d = calcular_distribuicao(1, 34, 33, 33)
    assert (d.faceis, d.medias, d.dificeis) == (1, 0, 0)


@pytest.mark.parametrize(
    ("percentuais", "esperado"),
    [((100, 0, 0), (10, 0, 0)), ((0, 0, 100), (0, 0, 10)), ((0, 100, 0), (0, 10, 0))],
)
def test_faixa_unica_leva_tudo(percentuais, esperado):
    d = calcular_distribuicao(10, *percentuais)
    assert (d.faceis, d.medias, d.dificeis) == esperado


def test_total_confere_com_o_n_pedido():
    d = calcular_distribuicao(29, 33, 33, 34)
    assert d.total() == 29


def test_itens_devolve_as_faixas_na_ordem_de_dificuldade():
    """O laço itera sobre isto para gerar N questões por faixa."""
    d = calcular_distribuicao(47, 10, 60, 30)
    assert d.itens() == [
        (FaixaDificuldade.FACIL, 5),
        (FaixaDificuldade.MEDIA, 28),
        (FaixaDificuldade.DIFICIL, 14),
    ]


def test_percentuais_que_nao_somam_cem_sao_rejeitados():
    with pytest.raises(ParametrosInconsistentesException):
        calcular_distribuicao(10, 10, 10, 10)


def test_percentual_negativo_e_rejeitado_mesmo_somando_cem():
    """-10/60/50 soma 100 e passaria pela checagem de soma. divmod(-100, 100)
    devolve (-1, 0), produzindo contagem negativa com total() correto — erro
    que a invariante da soma não detecta."""
    with pytest.raises(ParametrosInconsistentesException):
        calcular_distribuicao(10, -10, 60, 50)


def test_n_menor_que_um_e_erro_de_programacao_nao_de_negocio():
    """ValueError e não ParametrosInconsistentesException: o problema não são
    os percentuais do docente, é o chamador."""
    with pytest.raises(ValueError):
        calcular_distribuicao(0, 10, 60, 30)


def test_contagens_sao_int_e_nunca_float():
    d = calcular_distribuicao(47, 10, 60, 30)
    for valor in (d.faceis, d.medias, d.dificeis, d.total()):
        assert isinstance(valor, int)
        assert not isinstance(valor, float)


def test_invariante_vale_para_toda_combinacao_valida():
    """Teste de propriedade: é isto que cobre as combinações que ninguém
    pensou em enumerar. A soma tem que bater sempre, e nenhuma contagem pode
    ser negativa."""
    for n in range(1, 61):
        for p_f in range(0, 101, 5):
            for p_m in range(0, 101 - p_f, 5):
                p_d = 100 - p_f - p_m
                d = calcular_distribuicao(n, p_f, p_m, p_d)
                assert d.total() == n, (n, p_f, p_m, p_d, d)
                assert min(d.faceis, d.medias, d.dificeis) >= 0, (n, p_f, p_m, p_d)


def test_invariante_nos_percentuais_que_o_passo_de_cinco_nao_cobre():
    """O laço acima anda de 5 em 5 para não ficar lento; 33/33/34 e vizinhos
    ficariam de fora, e são justamente os que geram empate."""
    for n in range(1, 61):
        for percentuais in [(33, 33, 34), (34, 33, 33), (33, 34, 33), (1, 1, 98)]:
            d = calcular_distribuicao(n, *percentuais)
            assert d.total() == n, (n, percentuais, d)


def test_dataclass_e_imutavel():
    d = DistribuicaoQuestoes(faceis=1, medias=2, dificeis=3)
    # frozen=True levanta FrozenInstanceError, que herda de AttributeError.
    # `pytest.raises(Exception)` passaria até com um TypeError acidental.
    with pytest.raises(AttributeError):
        d.faceis = 99
