import pytest

from backend.app.exceptions import FonteInvalidaException
from backend.app.schemas.geracao import FonteGerada
from backend.app.services.geracao.contexto import formatar_trechos, resolver_fontes
from backend.app.services.rag.retrieval_service import TrechoRecuperado

TRECHOS = [
    TrechoRecuperado(7, "P1", "página 12", "A busca em largura usa fila.", 0.9, 0.8),
    TrechoRecuperado(
        9, "S2", "slide 3", "A busca em profundidade usa pilha.", 0.7, 0.6
    ),
]


def test_formatar_trechos_prefixa_identificador_e_localizacao():
    assert formatar_trechos(TRECHOS) == (
        "[P1, página 12] A busca em largura usa fila.\n\n"
        "[S2, slide 3] A busca em profundidade usa pilha."
    )


def test_resolver_fontes_troca_identificador_por_id():
    fontes = [
        FonteGerada(identificador_material="S2", localizacao="slide 3", trecho_base="t")
    ]
    assert resolver_fontes(fontes, TRECHOS) == [(9, "slide 3", "t")]


def test_fonte_inventada_e_rejeitada():
    """Sem esta checagem a rastreabilidade seria ficção."""
    fontes = [
        FonteGerada(identificador_material="P9", localizacao="x", trecho_base="t")
    ]
    with pytest.raises(FonteInvalidaException) as capturado:
        resolver_fontes(fontes, TRECHOS)
    assert capturado.value.corpo()["identificador"] == "P9"
    assert capturado.value.corpo()["disponiveis"] == ["P1", "S2"]


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
