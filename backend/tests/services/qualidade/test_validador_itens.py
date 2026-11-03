"""Validador de forma — puro, sem banco e sem LLM."""

from dataclasses import replace

import pytest

from backend.app.domain import RegraQualidade
from backend.app.services.qualidade.validador_itens import (
    AlternativaAvaliavel,
    AspectoAvaliavel,
    ItemDiscursivo,
    ItemObjetivo,
    Violacao,
    cita_letra,
    enunciado_repetido,
    validar_discursiva,
    validar_objetiva,
)

LETRAS = "ABCDEFGHIJK"


def objetiva(
    textos: list[str],
    correta: str = "A",
    gemeos: tuple[str, ...] = ("B",),
    enunciado: str = "Qual estrutura a busca em largura utiliza?",
    trechos: tuple[str, ...] = ("A busca em largura usa uma fila.",),
    identificadores: tuple[str, ...] = ("P1",),
) -> ItemObjetivo:
    return ItemObjetivo(
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


def test_objetiva_limpa_nao_tem_violacao():
    assert validar_objetiva(objetiva(LIMPO)) == []


# --- (i): nenhuma alternativa excede 1,5× a média das demais ---


def test_alternativa_longa_viola_tamanho():
    textos = ["Usa uma fila de vértices ainda não visitados.", *LIMPO[1:]]
    violacoes = validar_objetiva(objetiva(textos, correta="B", gemeos=("C",)))
    assert regras(violacoes) == [RegraQualidade.TAMANHO_ALTERNATIVA]
    assert violacoes[0].alvo == "A"
    assert "8 palavras" in violacoes[0].detalhe


def test_fronteira_exata_de_1_5x_nao_viola():
    # A tem 3 palavras; média das demais = (2 + 2) / 2 = 2; 3 == 1,5 × 2.
    textos = ["Usa uma fila.", "Usa pilha.", "Usa heap."]
    assert validar_objetiva(objetiva(textos, correta="B", gemeos=("C",))) == []


def test_um_acima_da_fronteira_viola():
    textos = ["Usa uma fila curta.", "Usa pilha.", "Usa heap."]
    violacoes = validar_objetiva(objetiva(textos, correta="B", gemeos=("C",)))
    assert regras(violacoes) == [RegraQualidade.TAMANHO_ALTERNATIVA]


def test_k_2_compara_com_a_unica_outra():
    # 3 contra 2 = 1,5× exato: não viola. 4 contra 2: viola.
    assert (
        validar_objetiva(
            objetiva(["Usa uma fila.", "Usa pilha."], correta="B", gemeos=("A",))
        )
        == []
    )
    violacoes = validar_objetiva(
        objetiva(["Usa uma fila curta.", "Usa pilha."], correta="B", gemeos=("A",))
    )
    assert regras(violacoes) == [RegraQualidade.TAMANHO_ALTERNATIVA]


def test_alternativa_vazia_nao_quebra():
    textos = ["", "Usa pilha.", "Usa heap.", "Usa lista."]
    assert validar_objetiva(objetiva(textos, correta="B", gemeos=("C",))) == []


# --- (ii): correta no máximo 20% maior que a errada mais longa ---


def test_fronteira_exata_de_1_2x_nao_viola():
    # correta 6 palavras, errada mais longa 5: 6 == 1,2 × 5.
    textos = [
        "um dois tres quatro cinco seis",
        "um dois tres quatro cinco",
        "um dois tres quatro cinco",
        "um dois tres quatro cinco",
    ]
    assert validar_objetiva(objetiva(textos)) == []


def test_correta_longa_viola():
    textos = [
        "um dois tres quatro cinco seis sete",
        "um dois tres quatro cinco",
        "um dois tres quatro cinco",
        "um dois tres quatro cinco",
    ]
    violacoes = validar_objetiva(objetiva(textos))
    assert regras(violacoes) == [RegraQualidade.CORRETA_LONGA]
    assert violacoes[0].alvo == "A"


# --- (iii): termos absolutos, salvo se o trecho-base os usa ---


def test_termo_absoluto_viola_com_pontuacao_e_caixa():
    textos = ["NUNCA, usa fila.", "Usa pilha.", "Usa heap.", "Sempre. usa lista"]
    violacoes = validar_objetiva(objetiva(textos))
    assert regras(violacoes) == [
        RegraQualidade.TERMO_ABSOLUTO,
        RegraQualidade.TERMO_ABSOLUTO,
    ]
    assert [v.alvo for v in violacoes] == ["A", "D"]


def test_termo_absoluto_no_enunciado_viola():
    violacoes = validar_objetiva(
        objetiva(LIMPO, enunciado="O percurso sempre usa qual estrutura?")
    )
    assert regras(violacoes) == [RegraQualidade.TERMO_ABSOLUTO]
    assert violacoes[0].alvo == "enunciado"


def test_termo_absoluto_sustentado_pelo_trecho_base_nao_viola():
    # Correta em B: "Sempre usa fila." (3 palavras) como correta dispararia
    # correta_longa contra erradas de 2.
    textos = ["Sempre usa fila.", "Usa pilha.", "Usa heap.", "Usa lista."]
    trechos = ("A busca em largura sempre usa uma fila.",)
    assert (
        validar_objetiva(objetiva(textos, correta="B", gemeos=("C",), trechos=trechos))
        == []
    )


def test_palavra_que_contem_termo_absoluto_nao_viola():
    textos = ["Usa sempreviva.", "Usa pilha.", "Usa heap.", "Usa lista."]
    assert validar_objetiva(objetiva(textos)) == []


# --- (iv): nenhuma referência de fonte no corpo ---


def test_mencao_a_slide_no_enunciado_viola():
    violacoes = validar_objetiva(
        objetiva(LIMPO, enunciado="Segundo o slide, qual estrutura?")
    )
    assert regras(violacoes) == [RegraQualidade.MENCAO_FONTE]
    assert violacoes[0].alvo == "enunciado"


def test_identificador_de_material_enviado_viola():
    # Duas palavras, como as demais: isola a regra (iv) das regras de tamanho.
    textos = ["Usa P1.", "Usa pilha.", "Usa heap.", "Usa lista."]
    violacoes = validar_objetiva(objetiva(textos, correta="B", gemeos=("C",)))
    assert regras(violacoes) == [RegraQualidade.MENCAO_FONTE]
    assert "P1" in violacoes[0].detalhe


def test_termo_de_conteudo_parecido_com_identificador_nao_viola():
    """ "cache L2" é conteúdo de computação. Só é violação se L2 for um material
    enviado nesta chamada."""
    violacoes = validar_objetiva(
        objetiva(LIMPO, enunciado="Qual estrutura aproveita melhor a cache L2?")
    )
    assert violacoes == []


def test_pdf_e_detectado_sem_distinguir_caixa():
    textos = ["Usa fila.", "Usa Pdf.", "Usa heap.", "Usa lista."]
    assert regras(validar_objetiva(objetiva(textos))) == [RegraQualidade.MENCAO_FONTE]


# --- densidade de gêmeos malvados ---


def test_k5_com_um_gemeo_passa():
    textos = ["Usa fila.", "Usa pilha.", "Usa heap.", "Usa lista.", "Usa vetor."]
    assert validar_objetiva(objetiva(textos, gemeos=("B",))) == []


def test_k6_com_um_gemeo_viola():
    textos = [
        "Usa fila.",
        "Usa pilha.",
        "Usa heap.",
        "Usa lista.",
        "Usa vetor.",
        "Usa mapa.",
    ]
    violacoes = validar_objetiva(objetiva(textos, gemeos=("B",)))
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
    assert validar_objetiva(objetiva(textos, gemeos=("B", "C"))) == []


def test_gemeo_na_correta_viola_e_nao_conta_como_gemeo():
    violacoes = validar_objetiva(objetiva(LIMPO, gemeos=("A",)))
    assert regras(violacoes) == [
        RegraQualidade.GEMEOS_INSUFICIENTES,
        RegraQualidade.GEMEO_NA_CORRETA,
    ]
    assert violacoes[1].alvo == "A"


# --- Contrato ---


def test_ordem_segue_a_tabela_de_regras():
    textos = ["Usa uma fila de vértices ainda não visitados.", *LIMPO[1:]]
    violacoes = validar_objetiva(
        objetiva(
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


# --- Discursiva ---


def discursiva(
    enunciado: str = "Explique por que a busca em largura usa uma fila.",
    aspectos: tuple[str, ...] = ("visita por camadas", "fila preserva a ordem"),
    trecho: str = "A busca em largura usa uma fila.",
    identificadores: tuple[str, ...] = ("P1",),
) -> ItemDiscursivo:
    return ItemDiscursivo(
        enunciado=enunciado,
        aspectos=[AspectoAvaliavel(texto=a, trecho_base=trecho) for a in aspectos],
        identificadores_fonte=list(identificadores),
    )


def test_discursiva_limpa_nao_tem_violacao():
    assert validar_discursiva(discursiva()) == []


@pytest.mark.parametrize(
    "enunciado",
    ["EXPLIQUE, com suas palavras, a busca.", "Compare: largura e profundidade."],
)
def test_comando_com_pontuacao_e_caixa_casa(enunciado):
    assert validar_discursiva(discursiva(enunciado=enunciado)) == []


@pytest.mark.parametrize(
    "enunciado",
    [
        "Qual estrutura a busca em largura usa?",
        "Faça uma explicação da busca em largura.",
        "Dê um exemplo comparativo entre as buscas.",
    ],
)
def test_sem_verbo_de_comando_viola(enunciado):
    violacoes = validar_discursiva(discursiva(enunciado=enunciado))
    assert regras(violacoes) == [RegraQualidade.COMANDO_AUSENTE]
    assert violacoes[0].alvo == "enunciado"


def test_termo_absoluto_no_enunciado_discursivo_viola():
    violacoes = validar_discursiva(
        discursiva(enunciado="Explique por que a busca sempre termina.")
    )
    assert regras(violacoes) == [RegraQualidade.TERMO_ABSOLUTO]


def test_termo_absoluto_liberado_pelo_trecho_de_um_aspecto():
    item = discursiva(
        enunciado="Explique por que a busca sempre termina.",
        trecho="Em grafo finito, a busca sempre termina.",
    )
    assert validar_discursiva(item) == []


def test_mencao_fonte_no_enunciado_viola():
    violacoes = validar_discursiva(
        discursiva(enunciado="Explique, conforme o slide, a busca em largura.")
    )
    assert regras(violacoes) == [RegraQualidade.MENCAO_FONTE]


def test_mencao_fonte_nos_aspectos_e_permitida():
    """Aspectos são para o docente: citar a fonte neles é legítimo."""
    item = discursiva(aspectos=("como no slide P1, visita por camadas", "usa fila"))
    assert validar_discursiva(item) == []


def test_aspectos_repetidos_violam_uma_vez_por_repeticao():
    item = discursiva(aspectos=("Usa fila.", "visita por camadas", "usa  FILA"))
    violacoes = validar_discursiva(item)
    assert regras(violacoes) == [RegraQualidade.ASPECTOS_REPETIDOS]
    assert violacoes[0].alvo == "aspecto 3"


def test_ordem_da_discursiva_segue_a_tabela():
    item = discursiva(
        enunciado="Segundo o slide, qual estrutura sempre é usada?",
        aspectos=("usa fila", "usa fila"),
    )
    assert regras(validar_discursiva(item)) == [
        RegraQualidade.TERMO_ABSOLUTO,
        RegraQualidade.MENCAO_FONTE,
        RegraQualidade.COMANDO_AUSENTE,
        RegraQualidade.ASPECTOS_REPETIDOS,
    ]


# --- invalidação ligada à letra e letra citada em texto ---


def item_com(**extras) -> ItemObjetivo:
    return replace(objetiva(LIMPO), **extras)


def regras_de(item: ItemObjetivo) -> list[RegraQualidade]:
    return regras(validar_objetiva(item))


def test_sem_campos_novos_nenhuma_regra_nova_dispara():
    assert regras_de(item_com()) == []


def test_invalidacoes_com_as_erradas_nao_violam():
    assert regras_de(item_com(invalidacoes=[("B", "x"), ("C", "y"), ("D", "z")])) == []


def test_letra_repetida_viola():
    extras = {"invalidacoes": [("B", "x"), ("B", "y"), ("D", "z")]}
    assert RegraQualidade.INVALIDACAO_LETRA_INVALIDA in regras_de(item_com(**extras))


def test_letra_da_correta_viola():
    extras = {"invalidacoes": [("A", "x"), ("C", "y"), ("D", "z")]}
    assert RegraQualidade.INVALIDACAO_LETRA_INVALIDA in regras_de(item_com(**extras))


def test_justificativa_que_cita_letra_viola():
    violacoes = validar_objetiva(
        item_com(justificativa_correta="A alternativa B confunde fila com pilha.")
    )
    assert [(v.regra, v.alvo) for v in violacoes] == [
        (RegraQualidade.LETRA_CITADA_EM_TEXTO, "justificativa")
    ]


def test_motivo_que_cita_letra_viola_com_o_alvo_da_invalidacao():
    extras = {"invalidacoes": [("B", "x"), ("C", "diferente da opção D"), ("D", "z")]}
    violacoes = validar_objetiva(item_com(**extras))
    assert (RegraQualidade.LETRA_CITADA_EM_TEXTO, "invalidacao C") in [
        (v.regra, v.alvo) for v in violacoes
    ]


def test_cita_letra_reconhece_as_tres_formas():
    assert cita_letra("veja a alternativa B")
    assert cita_letra("Letra (C) está errada")
    assert cita_letra("a opção D não se sustenta")
    assert cita_letra("ALTERNATIVA E")


def test_cita_letra_nao_confunde_conteudo():
    assert not cita_letra("a opção mais barata")
    assert not cita_letra("uma letra de câmbio")
    assert not cita_letra("a alternativa a ser marcada")
    assert not cita_letra("B está errada")  # limitação declarada


# --- ---

from backend.app.domain import FaixaDificuldade, FormatoItem  # noqa: E402

PROPOSICOES = [
    "Usa uma fila de vértices descobertos.",
    "Usa uma pilha de vértices descobertos.",
    "Usa um heap de vértices descobertos.",
    "Usa uma lista de vértices descobertos.",
]
CONTEXTO_15 = " ".join(["palavra"] * 15)
CONTEXTO_40 = " ".join(["palavra"] * 40)


def regras_de(item: ItemObjetivo) -> list[RegraQualidade]:
    return regras(validar_objetiva(item))


def com_comando(textos=PROPOSICOES, comando="Qual estrutura a busca usa?", **campos):
    base = objetiva(textos)
    return ItemObjetivo(
        enunciado=base.enunciado,
        alternativas=base.alternativas,
        trechos_base=base.trechos_base,
        identificadores_fonte=base.identificadores_fonte,
        comando=comando,
        **campos,
    )


def test_proposicao_completa_com_comando_nao_viola():
    assert regras_de(com_comando()) == []


def test_alternativa_rotulo_abaixo_de_quatro_palavras():
    violacoes = validar_objetiva(com_comando(LIMPO))
    assert regras(violacoes) == [RegraQualidade.ALTERNATIVA_ROTULO] * 4
    assert violacoes[0].alvo == "A"


def test_alternativa_rotulo_na_fronteira_exata():
    quatro = ["Usa uma fila agora.", *PROPOSICOES[1:]]
    tres = ["Usa uma fila.", *PROPOSICOES[1:]]
    assert RegraQualidade.ALTERNATIVA_ROTULO not in regras_de(com_comando(quatro))
    assert RegraQualidade.ALTERNATIVA_ROTULO in regras_de(com_comando(tres))


def test_sem_comando_regras_novas_de_alternativa_nao_disparam():
    """É o caso do auditor e dos itens antigos."""
    assert regras_de(objetiva(LIMPO)) == []


@pytest.mark.parametrize(
    "texto",
    ["Todas as anteriores estão certas.", "Nenhuma das opções acima se aplica."],
)
def test_alternativa_generica_com_e_sem_acento(texto):
    textos = [*PROPOSICOES[:3], texto]
    assert RegraQualidade.ALTERNATIVA_GENERICA in regras_de(com_comando(textos))


def test_comando_negativo_no_comando():
    item = com_comando(comando="Qual estrutura a busca NÃO usa?")
    assert regras_de(item) == [RegraQualidade.COMANDO_NEGATIVO]


def test_nao_do_contexto_nao_e_comando_negativo():
    item = com_comando(contexto="O sistema não usa recursão.")
    assert regras_de(item) == []


def test_pergunta_com_alternativa_minuscula_viola_pontuacao():
    textos = ["usa uma fila de vértices.", *PROPOSICOES[1:]]
    violacoes = validar_objetiva(com_comando(textos))
    assert regras(violacoes) == [RegraQualidade.PONTUACAO_INCOERENTE]
    assert violacoes[0].alvo == "A"


def test_frase_incompleta_com_alternativa_maiuscula_viola_pontuacao():
    item = com_comando(comando="Para guardar os vértices, a busca usa")
    assert regras_de(item) == [RegraQualidade.PONTUACAO_INCOERENTE] * 4


@pytest.mark.parametrize(
    "inicio",
    [
        "TCP como transporte da fila.",
        "12 vértices na fila agora.",
        r"\(n\) vértices na fila.",
    ],
)
def test_sigla_numero_e_formula_nao_contam_para_pontuacao(inicio):
    textos = [inicio, *(t.lower() for t in PROPOSICOES[1:])]
    item = com_comando(textos, comando="Para guardar os vértices, a busca usa")
    assert RegraQualidade.PONTUACAO_INCOERENTE not in regras_de(item)


@pytest.mark.parametrize(
    ("faixa", "contexto", "viola"),
    [
        (FaixaDificuldade.FACIL, "", False),
        (FaixaDificuldade.MEDIA, " ".join(["palavra"] * 14), True),
        (FaixaDificuldade.MEDIA, CONTEXTO_15, False),
        (FaixaDificuldade.DIFICIL, " ".join(["palavra"] * 39), True),
        (FaixaDificuldade.DIFICIL, CONTEXTO_40, False),
    ],
)
def test_contexto_curto_por_faixa_na_fronteira(faixa, contexto, viola):
    item = com_comando(faixa=faixa, contexto=contexto)
    assert (RegraQualidade.CONTEXTO_CURTO in regras_de(item)) is viola


def test_formato_montado_nao_mede_regras_de_alternativa():
    item = com_comando(LIMPO, formato=FormatoItem.AFIRMATIVAS)
    assert regras_de(item) == []


def test_afirmativas_mede_comando_negativo_e_assercao_nao():
    negativo = "Avalie as afirmações a seguir, exceto a última."
    assert regras_de(
        com_comando(comando=negativo, formato=FormatoItem.AFIRMATIVAS)
    ) == [RegraQualidade.COMANDO_NEGATIVO]
    assert (
        regras_de(com_comando(comando=negativo, formato=FormatoItem.ASSERCAO_RAZAO))
        == []
    )


def test_termo_absoluto_em_formato_montado_so_no_enunciado():
    textos = ["Usa sempre uma fila.", *PROPOSICOES[1:]]
    item = com_comando(textos, formato=FormatoItem.AFIRMATIVAS)
    assert RegraQualidade.TERMO_ABSOLUTO not in regras_de(item)


def test_assercao_que_copia_o_trecho_viola():
    item = com_comando(
        formato=FormatoItem.ASSERCAO_RAZAO,
        assercoes=["A busca em largura usa uma fila.", "Ela visita por camadas."],
    )
    violacoes = validar_objetiva(item)
    assert regras(violacoes) == [RegraQualidade.ASSERCAO_CITACAO]
    assert violacoes[0].alvo == "assercao"


def test_assercao_com_redacao_propria_nao_viola():
    item = com_comando(
        formato=FormatoItem.ASSERCAO_RAZAO,
        assercoes=[
            "Os vértices descobertos esperam numa fila.",
            "A ordem é de chegada.",
        ],
    )
    assert regras_de(item) == []


def test_discursiva_discuta_sozinho_e_comando_ausente():
    violacoes = validar_discursiva(discursiva(enunciado="Discuta a busca em largura."))
    assert regras(violacoes) == [RegraQualidade.COMANDO_AUSENTE]


def test_discursiva_calcule_e_comando():
    assert validar_discursiva(discursiva(enunciado="Calcule o custo da busca.")) == []


def test_discursiva_com_itens_mede_comando_e_opiniao_por_item():
    item = ItemDiscursivo(
        enunciado="contexto e itens",
        aspectos=[AspectoAvaliavel("visita por camadas", "trecho")],
        identificadores_fonte=["P1"],
        comandos=[
            ("item a", "Explique a busca."),
            ("item b", "Dê a sua opinião sobre a busca."),
        ],
    )
    violacoes = validar_discursiva(item)
    assert [(v.regra, v.alvo) for v in violacoes] == [
        (RegraQualidade.COMANDO_AUSENTE, "item b"),
        (RegraQualidade.OPINIAO_PESSOAL, "item b"),
    ]


def test_aspectos_repetidos_entre_itens():
    item = ItemDiscursivo(
        enunciado="x",
        aspectos=[
            AspectoAvaliavel("visita por camadas", "t"),
            AspectoAvaliavel("Visita por camadas.", "t"),
        ],
        identificadores_fonte=["P1"],
        comandos=[("item a", "Explique a busca."), ("item b", "Compare as buscas.")],
    )
    assert regras(validar_discursiva(item)) == [RegraQualidade.ASPECTOS_REPETIDOS]


def test_contexto_curto_na_discursiva():
    item = ItemDiscursivo(
        enunciado="Explique a busca.",
        aspectos=[AspectoAvaliavel("a", "t"), AspectoAvaliavel("b", "t")],
        identificadores_fonte=["P1"],
        faixa=FaixaDificuldade.DIFICIL,
        contexto=CONTEXTO_15,
    )
    assert regras(validar_discursiva(item)) == [RegraQualidade.CONTEXTO_CURTO]


# --- NOTACAO_INVALIDA ---


def _notacao(violacoes):
    return [v for v in violacoes if v.regra is RegraQualidade.NOTACAO_INVALIDA]


@pytest.mark.parametrize(
    ("texto", "trecho"),
    [
        (r"Seja \(x^2 sem fechar.", "delimitador"),
        (r"Seja \(\color{red}{x}\).", r"\color"),
        (r"Seja \(x^\).", "conversor"),
        ("Seja \\(a\nb\\).", "quebra de linha"),
    ],
)
def test_notacao_invalida_no_enunciado(texto, trecho):
    achadas = _notacao(validar_objetiva(item_com(enunciado=texto)))
    assert len(achadas) == 1
    assert achadas[0].alvo == "enunciado"
    assert trecho in achadas[0].detalhe


@pytest.mark.parametrize("barra_perdida", ["\frac", "\times", "\beta", "\neq"])
def test_barra_sem_escape_vira_violacao(barra_perdida):
    # No JSON, "\frac" sem a barra dobrada chega como U+000C + "rac".
    achadas = _notacao(
        validar_objetiva(
            item_com(enunciado=f"Calcule \\({barra_perdida}{{a}}{{b}}\\).")
        )
    )
    assert len(achadas) >= 1
    assert any(
        "controle" in v.detalhe or "quebra de linha" in v.detalhe for v in achadas
    )


def test_barra_sem_escape_fora_de_formula_tambem_e_pega():
    achadas = _notacao(validar_objetiva(item_com(enunciado="Calcule \frac{a}{b}.")))
    assert len(achadas) == 1
    assert "controle" in achadas[0].detalhe


def test_quebra_de_linha_fora_de_formula_e_legitima():
    assert (
        _notacao(validar_objetiva(item_com(enunciado="Linha um.\nLinha dois."))) == []
    )


def test_texto_sem_formula_nao_gera_violacao():
    assert _notacao(validar_objetiva(item_com(enunciado="O custo é R$ 50,00."))) == []


def test_formula_valida_nao_gera_violacao():
    texto = r"Seja \(\frac{a}{b}\) e \[\sum_{i=1}^{n} i\]."
    assert _notacao(validar_objetiva(item_com(enunciado=texto))) == []


def test_notacao_vale_para_alternativa_justificativa_e_invalidacao():
    base = objetiva(LIMPO)
    alternativas = [
        replace(base.alternativas[0], texto=r"Vale \(\color{red}{a}\) sempre assim."),
        *base.alternativas[1:],
    ]
    item = replace(
        base,
        alternativas=alternativas,
        justificativa_correta=r"Porque \(\href{x}{y}\).",
        texto_verificacao_unicidade=r"Só A \(x^\) serve.",
        invalidacoes=[("B", r"Erra em \(x^\).")],
    )
    alvos = {v.alvo for v in _notacao(validar_objetiva(item))}
    assert {"A", "justificativa", "verificacao", "invalidacao B"} <= alvos


def test_alternativa_so_formula_nao_e_rotulo():
    formulas = [rf"\(\frac{{1}}{{{n}}}\)" for n in range(2, 7)]
    item = com_comando(textos=formulas, comando="Qual o valor?")
    assert [
        v
        for v in validar_objetiva(item)
        if v.regra is RegraQualidade.ALTERNATIVA_ROTULO
    ] == []


def test_discursiva_mede_notacao_em_aspecto_e_comando():
    item = ItemDiscursivo(
        enunciado="Calcule.",
        aspectos=[AspectoAvaliavel(texto=r"Usa \(\color{red}{a}\).", trecho_base="t")],
        identificadores_fonte=["P1"],
        comandos=[("item a", r"Calcule \(\color{red}{x}\).")],
    )
    alvos = {v.alvo for v in _notacao(validar_discursiva(item))}
    assert {"item a", "aspecto 1"} <= alvos


def test_discursiva_contexto_dentro_do_enunciado_nao_duplica():
    contexto = r"Seja \(\color{red}{x}\) dado."
    item = ItemDiscursivo(
        enunciado=f"{contexto}\nExplique por que isso vale.",
        aspectos=[AspectoAvaliavel(texto="ok", trecho_base="t")],
        identificadores_fonte=["P1"],
        contexto=contexto,
    )
    assert len(_notacao(validar_discursiva(item))) == 1


# --- FORMULA_FORA_DO_TRECHO e NUMERO_NO_TEXTO ---


def _regras_calculo(**campos):
    return [
        v.regra
        for v in validar_objetiva(item_com(formato=FormatoItem.CALCULO, **campos))
    ]


def test_formula_fora_do_trecho():
    regras_ = _regras_calculo(
        formula_citada="v = sqrt(2gh)",
        texto_dos_trechos=["A velocidade final é v = raiz de 2gh."],
    )
    assert regras_.count(RegraQualidade.FORMULA_FORA_DO_TRECHO) == 1


def test_formula_no_trecho_com_espacos_diferentes_nao_gera():
    regras_ = _regras_calculo(
        formula_citada="v  =  sqrt(2gh)",
        texto_dos_trechos=["Vale v = sqrt(2gh) para queda."],
    )
    assert RegraQualidade.FORMULA_FORA_DO_TRECHO not in regras_


def test_formula_sem_trechos_nao_mede():
    assert RegraQualidade.FORMULA_FORA_DO_TRECHO not in _regras_calculo(
        formula_citada="v = x"
    )


@pytest.mark.parametrize(
    "texto",
    ["A altura é 9,8 m.", "A altura é 9.8 m.", "Com 9,81 m de queda."],
)
def test_numero_do_dado_no_texto(texto):
    regras_ = _regras_calculo(
        contexto=texto,
        comando="Calcule.",
        dados_calculo=[("g", 9.8, "m/s**2"), ("h", 9.81, "m")],
    )
    assert RegraQualidade.NUMERO_NO_TEXTO in regras_


def test_numero_que_nao_e_de_dado_nao_conta():
    regras_ = _regras_calculo(
        contexto="Há 3 tanques e 2 etapas.",
        comando="Calcule.",
        dados_calculo=[("n", 2.0, ""), ("h", 5.0, "m")],
    )
    assert RegraQualidade.NUMERO_NO_TEXTO not in regras_


def test_inteiro_com_unidade_so_casa_seguido_da_unidade():
    dados = [("d", 2.0, "m")]
    assert RegraQualidade.NUMERO_NO_TEXTO not in _regras_calculo(
        contexto="São 2 etapas.", comando="Calcule.", dados_calculo=dados
    )
    assert RegraQualidade.NUMERO_NO_TEXTO in _regras_calculo(
        contexto="Anda 2 m de altura.", comando="Calcule.", dados_calculo=dados
    )


def test_dado_sem_unidade_com_tres_digitos_casa():
    assert RegraQualidade.NUMERO_NO_TEXTO in _regras_calculo(
        contexto="A constante vale 273.",
        comando="Calcule.",
        dados_calculo=[("T", 273.0, "")],
    )


def test_dado_sem_unidade_com_dois_digitos_nao_casa():
    """Sem unidade, só decimal ou inteiro de três dígitos ou mais é "forte": um
    inteiro pequeno como 12 aparece no texto por outros motivos ("12 etapas")."""
    assert RegraQualidade.NUMERO_NO_TEXTO not in _regras_calculo(
        contexto="O processo tem 12 etapas.",
        comando="Calcule.",
        dados_calculo=[("n", 12.0, "")],
    )


def test_numero_decimal_nao_casa_dentro_de_outro_numero():
    assert RegraQualidade.NUMERO_NO_TEXTO not in _regras_calculo(
        contexto="Vale 9,81 m.", comando="Calcule.", dados_calculo=[("g", 9.8, "m")]
    )


def test_calculo_nao_aplica_regras_de_alternativa():
    base = objetiva([r"\(9{,}90\)", r"\(4{,}95\)", r"\(19{,}8\)", r"\(7{,}00\)"])
    item = replace(base, formato=FormatoItem.CALCULO, comando="Qual o valor?")
    regras_ = {v.regra for v in validar_objetiva(item)}
    assert not regras_ & {
        RegraQualidade.ALTERNATIVA_ROTULO,
        RegraQualidade.TAMANHO_ALTERNATIVA,
    }


# --- enunciado_repetido: os dois lados do limiar (0,9) ---

ORIGINAL = (
    "Qual estrutura de dados a busca em largura utiliza para guardar os vértices "
    "descobertos?"
)


def test_copia_com_caixa_e_pontuacao_diferentes_e_repetida():
    copia = ORIGINAL.upper().replace("?", "!")
    assert enunciado_repetido(copia, ORIGINAL)


def test_uma_palavra_trocada_ainda_e_repetida():
    """Razão 0,93: acima do limiar, é a mesma pergunta com um sinônimo."""
    quase = ORIGINAL.replace("guardar", "manter")
    assert enunciado_repetido(quase, ORIGINAL)


def test_variacao_legitima_abaixo_do_limiar_nao_e_repetida():
    """Razão 0,79: outra busca, outro conjunto de vértices. Com o limiar antigo
    de 0,8 já passava raspando; um limiar frouxo a recusaria como cópia."""
    variacao = (
        "Que estrutura de dados a busca em profundidade utiliza para guardar os "
        "vértices visitados?"
    )
    assert not enunciado_repetido(variacao, ORIGINAL)
