import pytest

from backend.app.services.geracao.plano_calculo import (
    contagens_de_calculo,
    posicoes_de_calculo,
    repartir,
)


def test_repartir_maior_resto():
    assert repartir(7, [10, 0, 0]) == [7, 0, 0]
    assert sum(repartir(5, [3, 3, 3])) == 5
    assert repartir(0, [4, 4]) == [0, 0]
    assert repartir(3, [0, 0]) == [0, 0]


@pytest.mark.parametrize(
    ("n", "p", "esperado"),
    [(10, 0, 0), (10, 100, 10), (10, 70, 7), (3, 50, 2), (7, 30, 2), (25, 10, 3)],
)
def test_n_calculo_pelo_maior_resto(n, p, esperado):
    assert sum(contagens_de_calculo(n, p, [n, 0, 0])) == esperado


def test_repartido_entre_faixas_nunca_passa_do_numero_de_objetivas():
    for faixas in ([4, 3, 3], [1, 1, 8], [0, 5, 5], [7, 0, 0]):
        n = sum(faixas)
        for p in range(0, 101, 5):
            c = contagens_de_calculo(n, p, faixas)
            assert all(ci <= fi for ci, fi in zip(c, faixas, strict=True))


def test_posicoes_equidistantes():
    assert posicoes_de_calculo(10, 2) == {0, 5}
    assert posicoes_de_calculo(10, 3) == {0, 3, 6}
    assert posicoes_de_calculo(4, 4) == {0, 1, 2, 3}
    assert posicoes_de_calculo(5, 0) == set()
