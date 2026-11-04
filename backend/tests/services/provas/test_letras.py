import pytest

from backend.app.exceptions import PlanoDeLetrasImpossivelException
from backend.app.services.provas import letras as mod
from backend.app.services.provas.letras import (
    JANELA_MONOTONA,
    periodo_minimo,
    planejar_letras,
    tem_deriva_monotona,
    tem_progressao_aritmetica,
)


def indices(texto: str) -> list[int]:
    return ["ABCDEFGHIJK".index(c) for c in texto]


# --- As quatro famílias de padrão, uma a uma ---


def test_familia_repeticao_constante():
    """Regra 2 do RF: ausência de sequência de >= 3 respostas iguais. É o passo
    zero da progressão aritmética."""
    assert tem_progressao_aritmetica(indices("AAA"))
    assert tem_progressao_aritmetica(indices("BAAAC"))


def test_familia_progressao_aritmetica():
    assert tem_progressao_aritmetica(indices("ABC"))
    assert tem_progressao_aritmetica(indices("ACE"))
    assert tem_progressao_aritmetica(indices("CBA"))
    assert tem_progressao_aritmetica(indices("EDC"))


def test_familia_periodo_curto():
    """AABAABAABAAB tem período 3 em 12 posições."""
    seq = indices("AABAABAABAAB")
    assert periodo_minimo(seq) == 3
    assert periodo_minimo(seq) * 2 <= len(seq)


def test_periodo_que_cobre_exatamente_metade_e_rejeitado():
    """ABDABD: período 3 em 6 posições, a fronteira exata do `* 2 <= n`. Sem
    progressão aritmética nem deriva monótona, então só a regra do período o
    recusa."""
    seq = indices("ABDABD")
    assert periodo_minimo(seq) * 2 == len(seq)
    assert not tem_progressao_aritmetica(seq)
    assert not tem_deriva_monotona(seq)
    assert mod._aceitavel(seq, None, 3) is False


def test_familia_deriva_monotona():
    """O furo que os três primeiros filtros deixavam passar. AABBCCDDEE é
    não-decrescente nas 10 posições, e EDCBA é o espelho descendente."""
    assert tem_deriva_monotona(indices("AABBCCDDEE"))
    assert tem_deriva_monotona(indices("EDCBA"))


# --- Casos que NÃO devem ser rejeitados ---


def test_alternancia_nao_tem_deriva_monotona():
    """ABABABABAB não é pego pela deriva — quem o rejeita é o período. Se
    alguém trocar um filtro pelo outro em vez de somar, este teste acusa."""
    seq = indices("ABABABABAB")
    assert not tem_deriva_monotona(seq)
    assert periodo_minimo(seq) * 2 <= len(seq)


def test_sequencia_legitima_com_corrida_curta_passa():
    """AABABBABAA tem corrida monótona de 3 e deve passar: filtro que engole
    sequência legítima faz o planejador estourar tentativas sem motivo."""
    seq = indices("AABABBABAA")
    assert not tem_deriva_monotona(seq)


def test_sequencia_curta_nao_cabe_na_janela():
    """Com 4 posições, a janela de 5 não existe."""
    assert not tem_deriva_monotona(indices("ABCD"))


def test_janela_monotona_e_cinco():
    """Constante do requisito operacionalizado, não configuração."""
    assert JANELA_MONOTONA == 5


# --- planejar_letras ---


@pytest.mark.parametrize("n", [10, 15, 20, 25])
@pytest.mark.parametrize("k", [2, 3, 5, 8, 11])
def test_plano_satisfaz_as_quatro_regras(n, k):
    plano = planejar_letras(n, k, semente=f"{n}-{k}")
    i = indices("".join(plano))

    assert len(plano) == n
    # Regra 1: diferença máxima de 1 entre quaisquer duas letras.
    contagens = [i.count(letra) for letra in range(k)]
    assert max(contagens) - min(contagens) <= 1
    # Regras 2 e 3.
    assert not tem_progressao_aritmetica(i)
    assert periodo_minimo(i) * 2 > n
    assert not tem_deriva_monotona(i)


def test_plano_respeita_o_teto_de_colisao_com_a_outra_prova():
    """Regra 4: <= 50% das posições com a mesma letra entre A e B."""
    a = planejar_letras(10, 5, semente="A")
    b = planejar_letras(10, 5, semente="B", contra=a)
    colisoes = sum(1 for x, y in zip(a, b, strict=True) if x == y)
    assert colisoes * 2 <= 10


def test_prova_so_de_discursivas_nao_tem_letra():
    assert planejar_letras(0, 5, semente="A") == []


def test_mesma_semente_mesmo_plano():
    """Determinismo é requisito: a mesma montagem sobre o mesmo banco tem de
    produzir o mesmo plano, ou a auditoria não reproduz."""
    assert planejar_letras(15, 5, semente="x") == planejar_letras(15, 5, semente="x")


def test_sementes_diferentes_planos_diferentes():
    assert planejar_letras(15, 5, semente="x") != planejar_letras(15, 5, semente="y")


def test_esgotar_tentativas_levanta(monkeypatch):
    """Filtro impossível: teto 1 com semente que não passa. A exceção existe
    para não haver laço infinito, não porque se espere atingi-la."""
    monkeypatch.setattr(mod, "MAX_TENTATIVAS_LETRAS", 1)
    monkeypatch.setattr(mod, "tem_deriva_monotona", lambda *_args, **_kwargs: True)
    with pytest.raises(PlanoDeLetrasImpossivelException):
        planejar_letras(10, 5, semente="qualquer")


def test_periodo_nao_exige_divisibilidade():
    """ABDABDABDA repete ABD com rabo truncado: período 3 em 10 posições. Exigir
    que o período divida o comprimento deixava esse padrão passar em todos os
    filtros."""
    seq = indices("ABDABDABDA")
    assert periodo_minimo(seq) == 3
    assert not tem_progressao_aritmetica(seq)
    assert not tem_deriva_monotona(seq)


@pytest.mark.parametrize("n", range(1, 26))
def test_par_de_planos_existe_para_todo_n(n):
    """Com 1 posição objetiva o teto de colisão é 0: B precisa de letra diferente
    de A. Dar o resto sempre às primeiras letras fazia A e B receberem `A`, e a
    prova com 1 objetiva e várias discursivas estourava."""
    for k in (2, 5, 11):
        a = planejar_letras(n, k, semente=f"A{n}-{k}")
        b = planejar_letras(n, k, semente=f"B{n}-{k}", contra=a)
        colisoes = sum(1 for x, y in zip(a, b, strict=True) if x == y)
        assert colisoes * 2 <= n


def test_planos_de_tamanhos_diferentes_limitam_colisao_nas_posicoes_comuns():
    """A e B escolhidas pelo docente podem ter números diferentes de objetivas."""
    contra = planejar_letras(7, 5, "a")
    plano = planejar_letras(8, 5, "b", contra=contra)
    assert len(plano) == 8
    colisoes = sum(1 for x, y in zip(plano, contra, strict=False) if x == y)
    assert colisoes <= 7 // 2
