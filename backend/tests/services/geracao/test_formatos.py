import pytest

from backend.app.domain import FaixaDificuldade, FormatoItem
from backend.app.schemas.geracao import n_afirmativas
from backend.app.services.geracao.formatos import (
    CONFIGURACOES_ASSERCAO,
    atribuir_configuracao,
    atribuir_formato,
    atribuir_n_itens,
    configuracoes_afirmativas,
)

F, M, D = FaixaDificuldade.FACIL, FaixaDificuldade.MEDIA, FaixaDificuldade.DIFICIL
P, A, R = FormatoItem.PROPOSICAO, FormatoItem.AFIRMATIVAS, FormatoItem.ASSERCAO_RAZAO


def _sequencia(faixa, k, n=6):
    return [atribuir_formato(faixa, i, k) for i in range(n)]


def test_facil_e_sempre_proposicao():
    assert set(_sequencia(F, 5)) == {P}


def test_media_alterna_proposicao_e_afirmativas():
    assert _sequencia(M, 5, 4) == [P, A, P, A]


def test_dificil_com_k5_alterna_os_tres_na_ordem_da_tabela():
    assert _sequencia(D, 5) == [P, A, R, P, A, R]


def test_dificil_com_k4_nao_tem_assercao():
    assert _sequencia(D, 4, 4) == [P, A, P, A]


@pytest.mark.parametrize("k", [2, 3])
def test_k_pequeno_so_tem_proposicao(k):
    for faixa in (F, M, D):
        assert set(_sequencia(faixa, k)) == {P}


def test_mesma_posicao_mesmo_formato():
    assert atribuir_formato(D, 7, 5) == atribuir_formato(D, 7, 5)


def test_n_afirmativas_por_k():
    assert [n_afirmativas(k) for k in (4, 7, 8, 11)] == [3, 3, 4, 4]


def test_configuracoes_de_tres_afirmativas_alternam_tamanhos():
    v, f = True, False
    assert configuracoes_afirmativas(3) == [
        (v, v, f),
        (v, f, f),
        (v, v, v),
        (v, f, v),
        (f, v, f),
        (f, v, v),
        (f, f, v),
    ]


def test_configuracoes_nunca_tem_nenhuma_verdadeira():
    for n in (3, 4):
        assert all(any(c) for c in configuracoes_afirmativas(n))
    assert len(configuracoes_afirmativas(4)) == 15


def test_configuracao_por_rodizio():
    opcoes = configuracoes_afirmativas(3)
    assert atribuir_configuracao(A, 0, 5) == opcoes[0]
    assert atribuir_configuracao(A, 8, 5) == opcoes[1]
    assert atribuir_configuracao(R, 0, 5) == CONFIGURACOES_ASSERCAO[0]
    assert atribuir_configuracao(R, 5, 5) == CONFIGURACOES_ASSERCAO[0]
    assert atribuir_configuracao(P, 3, 5) is None


def test_configuracao_de_afirmativas_com_k_grande_tem_quatro_posicoes():
    assert len(atribuir_configuracao(A, 0, 11)) == 4


def test_n_itens_so_na_dificil_e_alternando():
    assert atribuir_n_itens(F, 0) is None
    assert atribuir_n_itens(M, 3) is None
    assert [atribuir_n_itens(D, i) for i in range(4)] == [2, 3, 2, 3]


from backend.app.domain import TipoQuestao  # noqa: E402
from backend.app.schemas.geracao import montar_schema  # noqa: E402
from backend.app.services.geracao.formatos import (  # noqa: E402
    juntar,
    montar_discursiva,
    montar_proposicao,
    texto_contextualizacao,
)
from backend.tests.services.geracao.duplos import (  # noqa: E402
    CONTEXTO_MEDIA,
    corpo_discursiva,
    corpo_questao,
)


def _saida(tipo, corpo, k=5):
    return montar_schema(tipo, k).model_validate(corpo).resultado


def test_juntar_descarta_contexto_em_branco():
    assert juntar("   ", "Qual?") == "Qual?"
    assert juntar("Cenário.", "Qual?") == "Cenário.\n\nQual?"


def test_proposicao_monta_enunciado_e_pergunta():
    montada = montar_proposicao(
        _saida(TipoQuestao.OBJETIVA, corpo_questao(5, contexto=CONTEXTO_MEDIA))
    )
    assert montada.formato is FormatoItem.PROPOSICAO
    assert montada.enunciado == f"{CONTEXTO_MEDIA}\n\n{montada.comando}"
    assert montada.pergunta == montada.comando
    assert montada.estrutura_formato == {"contexto": CONTEXTO_MEDIA}
    assert [i.letra for i in montada.invalidacoes] == ["B", "C", "D", "E"]


def test_discursiva_sem_itens_monta_enunciado():
    montada = montar_discursiva(_saida(TipoQuestao.DISCURSIVA, corpo_discursiva()))
    assert montada.n_itens is None
    assert montada.enunciado == montada.comandos[0]
    assert [a.item for a in montada.aspectos] == [None, None]


def test_contextualizacao_por_faixa():
    assert "nenhuma" in texto_contextualizacao(F).lower()
    assert "aplicação" in texto_contextualizacao(M).lower()
    assert "cenário" in texto_contextualizacao(D).lower()


from backend.app.services.geracao.formatos import (  # noqa: E402
    ABERTURA_ITENS,
    FECHO_AFIRMATIVAS,
    TEXTO_ASSERCAO,
    montar_afirmativas,
    montar_assercao_razao,
    rotulo_combinacao,
    texto_pedido_formato,
)
from backend.tests.services.geracao.duplos import (  # noqa: E402
    corpo_afirmativas,
    corpo_assercao,
    corpo_discursiva_itens,
)

V, X = True, False


def _afirmativas(cfg, k=5, numero=1):
    saida = (
        montar_schema(TipoQuestao.OBJETIVA, k, A, cfg)
        .model_validate(corpo_afirmativas(cfg))
        .resultado
    )
    return montar_afirmativas(saida, cfg, k, numero)


def test_rotulos_no_padrao_enade():
    assert rotulo_combinacao((X, V, X)) == "II, apenas."
    assert rotulo_combinacao((V, X, V)) == "I e III, apenas."
    assert rotulo_combinacao((V, V, V)) == "I, II e III."
    assert rotulo_combinacao((V, V, X, V)) == "I, II e IV, apenas."


def test_afirmativas_monta_linhas_e_fecho():
    montada = _afirmativas((V, X, V))
    linhas = montada.pergunta.split("\n")
    assert linhas[2].startswith("I. ") and linhas[3].startswith("II. ")
    assert montada.enunciado.endswith(FECHO_AFIRMATIVAS)
    assert montada.enunciado.startswith(CONTEXTO_MEDIA)


def test_afirmativas_correta_e_a_configuracao_e_gemeos_a_distancia_1():
    montada = _afirmativas((V, X, V))
    textos = [a.texto for a in montada.alternativas]
    correta = textos["ABCDE".index(montada.letra_correta)]
    assert correta == "I e III, apenas."
    gemeos = sorted(a.texto for a in montada.alternativas if a.e_gemeo_malvado)
    assert gemeos == ["I, II e III.", "I, apenas.", "III, apenas."]


def test_afirmativas_completa_com_distancia_2_quando_faltam_vizinhos():
    montada = _afirmativas((V, X, X))  # vizinhos não vazios: (V,V,X) e (V,X,V)
    assert len(montada.alternativas) == 5
    assert sum(a.e_gemeo_malvado for a in montada.alternativas) == 2


def test_afirmativas_com_k_11_usa_quatro_afirmativas():
    cfg = (V, X, V, X)
    montada = _afirmativas(cfg, k=11)
    assert len(montada.alternativas) == 11
    assert len(set(a.texto for a in montada.alternativas)) == 11
    assert "IV. " in montada.pergunta


def test_afirmativas_posicao_reprodutivel_pela_semente():
    assert (
        _afirmativas((V, X, V), numero=7).letra_correta
        == _afirmativas((V, X, V), numero=7).letra_correta
    )


def test_afirmativas_posicao_da_correta_varia_com_o_numero():
    """A semente é o número da questão, não uma constante: com semente fixa, a
    correta cairia sempre na mesma letra em todas as questões de afirmativas,
    e o gabarito ficaria previsível. Reprodutível não é o mesmo que constante."""
    letras = {_afirmativas((V, X, V), numero=n).letra_correta for n in range(1, 21)}
    assert len(letras) > 1


def test_afirmativas_uma_invalidacao_por_distrator():
    montada = _afirmativas((V, X, V))
    letras = [i.letra for i in montada.invalidacoes]
    assert sorted(letras + [montada.letra_correta]) == list("ABCDE")
    assert montada.estrutura_formato["afirmativas"][1]["verdadeira"] is False
    assert montada.verificacao_unicidade is True


@pytest.mark.parametrize("cfg", list(TEXTO_ASSERCAO))
def test_assercao_correta_para_cada_configuracao(cfg):
    saida = (
        montar_schema(TipoQuestao.OBJETIVA, 5, R, cfg)
        .model_validate(corpo_assercao())
        .resultado
    )
    montada = montar_assercao_razao(saida, cfg, 3)
    textos = [a.texto for a in montada.alternativas]
    assert sorted(textos) == sorted(TEXTO_ASSERCAO.values())
    assert textos["ABCDE".index(montada.letra_correta)] == TEXTO_ASSERCAO[cfg]
    assert "\n\nPORQUE\n\n" in montada.enunciado
    assert montada.enunciado.endswith(
        "A respeito dessas asserções, assinale a opção correta."
    )
    assert montada.assercoes == [saida.assercao, saida.razao]
    assert montada.estrutura_formato["configuracao"] == cfg


def test_discursiva_com_itens_monta_letras_e_item_dos_aspectos():
    saida = (
        montar_schema(TipoQuestao.DISCURSIVA, 5, n_itens=2)
        .model_validate(corpo_discursiva_itens(2))
        .resultado
    )
    montada = montar_discursiva(saida)
    assert montada.n_itens == 2
    assert ABERTURA_ITENS in montada.enunciado
    assert "\na) " not in montada.enunciado.split(ABERTURA_ITENS)[0]
    assert montada.pergunta.split("\n\n")[1].startswith("a) ")
    assert [a.item for a in montada.aspectos] == [1, 2]


def test_pedido_descreve_a_configuracao():
    assert "a afirmativa II deve ser falsa" in texto_pedido_formato(A, (V, X, V), 5)
    assert "as afirmativas I e III devem ser verdadeiras" in texto_pedido_formato(
        A, (V, X, V), 5
    )
    assert "exatamente 5 alternativas" in texto_pedido_formato(P, None, 5)


# --- CALCULO ---


def test_pedido_do_formato_calculo_conta_os_erros():
    from backend.app.domain import FormatoItem
    from backend.app.services.geracao.formatos import texto_pedido_formato

    assert "3 erros típicos" in texto_pedido_formato(FormatoItem.CALCULO, None, 4)


def test_montar_objetiva_despacha_calculo():
    from types import SimpleNamespace

    from backend.app.domain import FormatoItem
    from backend.app.services.geracao.formatos import montar_objetiva

    saida = SimpleNamespace(
        contexto="Um objeto cai.",
        comando="Qual a velocidade?",
        dados=[
            SimpleNamespace(simbolo="g", valor=9.8, unidade="m/s**2"),
            SimpleNamespace(simbolo="h", valor=5.0, unidade="m"),
        ],
        formula_citada="v = sqrt(2gh)",
        expressao="sqrt(2 * g * h)",
        unidade_resultado="m/s",
        erros=[
            SimpleNamespace(descricao="a", expressao="sqrt(g * h)"),
            SimpleNamespace(descricao="b", expressao="sqrt(2 * g * h) / 2"),
            SimpleNamespace(descricao="c", expressao="sqrt(2 * g * h) * 2"),
        ],
        objetivo_cognitivo="aplicar",
        fontes=[],
        tema="t",
        subtema="s",
        nivel_bloom="aplicar",
    )
    montada = montar_objetiva(saida, FormatoItem.CALCULO, None, 4, 1)
    assert montada.formato is FormatoItem.CALCULO
