"""Validador de forma — puro, sem banco e sem LLM."""

from backend.app.domain import RegraQualidade
from backend.app.services.qualidade.validador_itens import (
    AlternativaAvaliavel,
    ItemAvaliavel,
    Violacao,
    validar_item,
)

LETRAS = "ABCDEFGHIJK"


def item(
    textos: list[str],
    correta: str = "A",
    gemeos: tuple[str, ...] = ("B",),
    enunciado: str = "Qual estrutura a busca em largura utiliza?",
    trechos: tuple[str, ...] = ("A busca em largura usa uma fila.",),
    identificadores: tuple[str, ...] = ("P1",),
) -> ItemAvaliavel:
    return ItemAvaliavel(
        enunciado=enunciado,
        alternativas=[
            AlternativaAvaliavel(
                letra=LETRAS[i],
                texto=texto,
                correta=LETRAS[i] == correta,
                e_gemeo_malvado=LETRAS[i] in gemeos,
            )
            for i, texto in enumerate(textos)
        ],
        trechos_base=list(trechos),
        identificadores_fonte=list(identificadores),
    )


def regras(violacoes: list[Violacao]) -> list[RegraQualidade]:
    return [v.regra for v in violacoes]


LIMPO = ["Usa fila.", "Usa pilha.", "Usa heap.", "Usa lista."]


def test_item_limpo_nao_tem_violacao():
    assert validar_item(item(LIMPO)) == []


# --- (i): nenhuma alternativa excede 1,5× a média das demais ---


def test_alternativa_longa_viola_tamanho():
    textos = ["Usa uma fila de vértices ainda não visitados.", *LIMPO[1:]]
    violacoes = validar_item(item(textos, correta="B", gemeos=("C",)))
    assert regras(violacoes) == [RegraQualidade.TAMANHO_ALTERNATIVA]
    assert violacoes[0].alvo == "A"
    assert "8 palavras" in violacoes[0].detalhe


def test_fronteira_exata_de_1_5x_nao_viola():
    # A tem 3 palavras; média das demais = (2 + 2) / 2 = 2; 3 == 1,5 × 2.
    textos = ["Usa uma fila.", "Usa pilha.", "Usa heap."]
    assert validar_item(item(textos, correta="B", gemeos=("C",))) == []


def test_um_acima_da_fronteira_viola():
    textos = ["Usa uma fila curta.", "Usa pilha.", "Usa heap."]
    violacoes = validar_item(item(textos, correta="B", gemeos=("C",)))
    assert regras(violacoes) == [RegraQualidade.TAMANHO_ALTERNATIVA]


def test_k_2_compara_com_a_unica_outra():
    # 3 contra 2 = 1,5× exato: não viola. 4 contra 2: viola.
    assert (
        validar_item(
            item(["Usa uma fila.", "Usa pilha."], correta="B", gemeos=("A",))
        )
        == []
    )
    violacoes = validar_item(
        item(["Usa uma fila curta.", "Usa pilha."], correta="B", gemeos=("A",))
    )
    assert regras(violacoes) == [RegraQualidade.TAMANHO_ALTERNATIVA]


def test_alternativa_vazia_nao_quebra():
    textos = ["", "Usa pilha.", "Usa heap.", "Usa lista."]
    assert validar_item(item(textos, correta="B", gemeos=("C",))) == []


# --- (ii): correta no máximo 20% maior que a errada mais longa ---


def test_fronteira_exata_de_1_2x_nao_viola():
    # correta 6 palavras, errada mais longa 5: 6 == 1,2 × 5.
    textos = [
        "um dois tres quatro cinco seis",
        "um dois tres quatro cinco",
        "um dois tres quatro cinco",
        "um dois tres quatro cinco",
    ]
    assert validar_item(item(textos)) == []


def test_correta_longa_viola():
    textos = [
        "um dois tres quatro cinco seis sete",
        "um dois tres quatro cinco",
        "um dois tres quatro cinco",
        "um dois tres quatro cinco",
    ]
    violacoes = validar_item(item(textos))
    assert regras(violacoes) == [RegraQualidade.CORRETA_LONGA]
    assert violacoes[0].alvo == "A"


# --- (iii): termos absolutos, salvo se o trecho-base os usa ---


def test_termo_absoluto_viola_com_pontuacao_e_caixa():
    textos = ["NUNCA, usa fila.", "Usa pilha.", "Usa heap.", "Sempre. usa lista"]
    violacoes = validar_item(item(textos))
    assert regras(violacoes) == [
        RegraQualidade.TERMO_ABSOLUTO,
        RegraQualidade.TERMO_ABSOLUTO,
    ]
    assert [v.alvo for v in violacoes] == ["A", "D"]


def test_termo_absoluto_no_enunciado_viola():
    violacoes = validar_item(item(LIMPO, enunciado="O percurso sempre usa qual estrutura?"))
    assert regras(violacoes) == [RegraQualidade.TERMO_ABSOLUTO]
    assert violacoes[0].alvo == "enunciado"


def test_termo_absoluto_sustentado_pelo_trecho_base_nao_viola():
    # Correta em B: "Sempre usa fila." (3 palavras) como correta dispararia
    # correta_longa contra erradas de 2.
    textos = ["Sempre usa fila.", "Usa pilha.", "Usa heap.", "Usa lista."]
    trechos = ("A busca em largura sempre usa uma fila.",)
    assert (
        validar_item(
            item(textos, correta="B", gemeos=("C",), trechos=trechos)
        )
        == []
    )


def test_palavra_que_contem_termo_absoluto_nao_viola():
    textos = ["Usa sempreviva.", "Usa pilha.", "Usa heap.", "Usa lista."]
    assert validar_item(item(textos)) == []


# --- (iv): nenhuma referência de fonte no corpo ---


def test_mencao_a_slide_no_enunciado_viola():
    violacoes = validar_item(
        item(LIMPO, enunciado="Segundo o slide, qual estrutura?")
    )
    assert regras(violacoes) == [RegraQualidade.MENCAO_FONTE]
    assert violacoes[0].alvo == "enunciado"


def test_identificador_de_material_enviado_viola():
    # Duas palavras, como as demais: isola a regra (iv) das regras de tamanho.
    textos = ["Usa P1.", "Usa pilha.", "Usa heap.", "Usa lista."]
    violacoes = validar_item(item(textos, correta="B", gemeos=("C",)))
    assert regras(violacoes) == [RegraQualidade.MENCAO_FONTE]
    assert "P1" in violacoes[0].detalhe


def test_termo_de_conteudo_parecido_com_identificador_nao_viola():
    """"cache L2" é conteúdo de computação. Só é violação se L2 for um material
    enviado nesta chamada."""
    violacoes = validar_item(
        item(LIMPO, enunciado="Qual estrutura aproveita melhor a cache L2?")
    )
    assert violacoes == []


def test_pdf_e_detectado_sem_distinguir_caixa():
    textos = ["Usa fila.", "Usa Pdf.", "Usa heap.", "Usa lista."]
    assert regras(validar_item(item(textos))) == [RegraQualidade.MENCAO_FONTE]


# --- densidade de gêmeos malvados ---


def test_k5_com_um_gemeo_passa():
    textos = ["Usa fila.", "Usa pilha.", "Usa heap.", "Usa lista.", "Usa vetor."]
    assert validar_item(item(textos, gemeos=("B",))) == []


def test_k6_com_um_gemeo_viola():
    textos = [
        "Usa fila.",
        "Usa pilha.",
        "Usa heap.",
        "Usa lista.",
        "Usa vetor.",
        "Usa mapa.",
    ]
    violacoes = validar_item(item(textos, gemeos=("B",)))
    assert regras(violacoes) == [RegraQualidade.GEMEOS_INSUFICIENTES]
    assert violacoes[0].alvo == "questao"


def test_k6_com_dois_gemeos_passa():
    textos = [
        "Usa fila.",
        "Usa pilha.",
        "Usa heap.",
        "Usa lista.",
        "Usa vetor.",
        "Usa mapa.",
    ]
    assert validar_item(item(textos, gemeos=("B", "C"))) == []


def test_gemeo_na_correta_viola_e_nao_conta_como_gemeo():
    violacoes = validar_item(item(LIMPO, gemeos=("A",)))
    assert regras(violacoes) == [
        RegraQualidade.GEMEOS_INSUFICIENTES,
        RegraQualidade.GEMEO_NA_CORRETA,
    ]
    assert violacoes[1].alvo == "A"


# --- Contrato ---


def test_ordem_segue_a_tabela_de_regras():
    textos = ["Usa uma fila de vértices ainda não visitados.", *LIMPO[1:]]
    violacoes = validar_item(
        item(
            textos,
            correta="B",
            gemeos=("C",),
            enunciado="No slide, qual estrutura?",
        )
    )
    assert regras(violacoes) == [
        RegraQualidade.TAMANHO_ALTERNATIVA,
        RegraQualidade.MENCAO_FONTE,
    ]


def test_como_dict_serializa_o_valor_do_enum():
    violacao = Violacao(RegraQualidade.MENCAO_FONTE, "enunciado", "menciona slide")
    assert violacao.como_dict() == {
        "regra": "mencao_fonte",
        "alvo": "enunciado",
        "detalhe": "menciona slide",
    }
