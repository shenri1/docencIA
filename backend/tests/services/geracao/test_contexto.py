import pytest

from backend.app.exceptions import FonteInvalidaException, FonteNaoSustentadaException
from backend.app.schemas.geracao import FonteGerada
from backend.app.services.geracao.contexto import formatar_trechos, resolver_fontes
from backend.app.services.rag.retrieval_service import TrechoRecuperado

TRECHOS = [
    TrechoRecuperado(1, 7, "P1", "página 12", "A busca em largura usa fila.", 0.9, 0.8),
    TrechoRecuperado(
        2, 9, "S2", "slide 3", "A busca em profundidade usa pilha.", 0.7, 0.6
    ),
]


def test_formatar_trechos_prefixa_identificador_e_localizacao():
    assert formatar_trechos(TRECHOS) == (
        "[P1, página 12] A busca em largura usa fila.\n\n"
        "[S2, slide 3] A busca em profundidade usa pilha."
    )


def test_resolver_fontes_troca_identificador_por_id():
    trecho = "A busca em profundidade usa pilha."
    fontes = [
        FonteGerada(
            identificador_material="S2", localizacao="slide 3", trecho_base=trecho
        )
    ]
    assert resolver_fontes(fontes, TRECHOS) == [(9, "slide 3", trecho)]


def test_fonte_inventada_e_rejeitada():
    """Sem esta checagem a rastreabilidade seria ficção."""
    fontes = [
        FonteGerada(identificador_material="P9", localizacao="x", trecho_base="t")
    ]
    with pytest.raises(FonteInvalidaException) as capturado:
        resolver_fontes(fontes, TRECHOS)
    assert capturado.value.corpo()["identificador"] == "P9"
    assert capturado.value.corpo()["disponiveis"] == ["P1", "S2"]


def _fonte(
    identificador="P1", localizacao="página 12", trecho="A busca em largura usa fila."
):
    return FonteGerada(
        identificador_material=identificador,
        localizacao=localizacao,
        trecho_base=trecho,
    )


def test_trecho_inventado_e_rejeitado():
    """Citar "P1" não basta: o trecho precisa existir no material citado."""
    with pytest.raises(FonteNaoSustentadaException) as capturado:
        resolver_fontes(
            [_fonte(trecho="O grafo é sempre acíclico por definição.")], TRECHOS
        )
    assert capturado.value.corpo()["identificador"] == "P1"


def test_trecho_de_outro_material_e_rejeitado():
    """O trecho existe, mas no S2: a fonte diz P1."""
    with pytest.raises(FonteNaoSustentadaException):
        resolver_fontes(
            [_fonte(trecho="A busca em profundidade usa pilha.")], TRECHOS
        )


def test_trecho_literal_ignora_caixa_espacos_e_aspas():
    fonte = _fonte(trecho="  a BUSCA em   largura\nusa fila. ")
    assert resolver_fontes([fonte], TRECHOS) == [
        (7, "página 12", "  a BUSCA em   largura\nusa fila. ")
    ]


def test_trecho_com_pequena_variacao_passa_pelo_limiar():
    fonte = _fonte(trecho="A busca em largura usa uma fila.")
    assert resolver_fontes([fonte], TRECHOS)[0][0] == 7


def test_trecho_parafraseado_e_rejeitado():
    fonte = _fonte(
        trecho="Para percorrer por níveis o algoritmo guarda os vértices em espera."
    )
    with pytest.raises(FonteNaoSustentadaException):
        resolver_fontes([fonte], TRECHOS)


def test_trecho_vazio_e_rejeitado():
    with pytest.raises(FonteNaoSustentadaException):
        resolver_fontes([_fonte(trecho="   ")], TRECHOS)


def test_localizacao_inexistente_vira_a_do_chunk_que_contem_o_trecho():
    """Trecho real, mas "página 99" não é onde ele está: grava a real."""
    assert resolver_fontes([_fonte(localizacao="página 99")], TRECHOS) == [
        (7, "página 12", "A busca em largura usa fila.")
    ]


def test_localizacao_de_outro_material_vira_a_do_material_citado():
    assert resolver_fontes([_fonte(localizacao="slide 3")], TRECHOS)[0][1] == (
        "página 12"
    )


def test_localizacao_mais_especifica_que_a_do_chunk_e_aceita():
    fonte = _fonte(localizacao="Página 12, parágrafo 3")
    assert resolver_fontes([fonte], TRECHOS)[0][1] == "Página 12, parágrafo 3"


def test_localizacao_de_chunk_combinado_aceita_qualquer_parte():
    trechos = [
        TrechoRecuperado(
            3, 7, "P1", "página 12; página 13", "A fila guarda a ordem.", 0.9, 0.8
        )
    ]
    assert resolver_fontes(
        [_fonte(localizacao="página 13", trecho="A fila guarda a ordem.")], trechos
    )
    # "página 1" não é "página 12" nem "página 13": palavras inteiras.
    assert resolver_fontes(
        [_fonte(localizacao="página 1", trecho="A fila guarda a ordem.")], trechos
    )[0][1] == "página 12; página 13"


def test_trecho_repetido_em_dois_chunks_aceita_a_localizacao_de_qualquer_um():
    trechos = [
        TrechoRecuperado(1, 7, "P1", "página 2", "A fila guarda a ordem.", 0.9, 0.8),
        TrechoRecuperado(2, 7, "P1", "página 5", "A fila guarda a ordem.", 0.9, 0.8),
    ]
    assert resolver_fontes(
        [_fonte(localizacao="página 5", trecho="A fila guarda a ordem.")], trechos
    )


def test_formatar_orientacoes_numera_e_combina():
    from types import SimpleNamespace

    from backend.app.services.geracao.contexto import formatar_orientacoes

    texto = formatar_orientacoes(
        [
            SimpleNamespace(o_que_mudar="exemplos práticos", cruzar_com=None),
            SimpleNamespace(o_que_mudar=None, cruzar_com="arquitetura de computadores"),
            SimpleNamespace(o_que_mudar="enunciado curto", cruzar_com="memória cache"),
        ]
    )
    assert texto == (
        "Orientações do docente:\n"
        "1. Mudar: exemplos práticos\n"
        "2. Articular com: arquitetura de computadores\n"
        "3. Articular com: memória cache. Mudar: enunciado curto"
    )


def test_formatar_orientacoes_vazio_e_none():
    from backend.app.services.geracao.contexto import formatar_orientacoes

    assert formatar_orientacoes([]) is None
    assert formatar_orientacoes(()) is None
