import pytest

from backend.app.exceptions import FonteInvalidaException
from backend.app.schemas.geracao import FonteGerada
from backend.app.services.geracao.contexto import formatar_trechos, resolver_fontes
from backend.app.services.rag.retrieval_service import TrechoRecuperado

TRECHOS = [
    TrechoRecuperado(7, "P1", "página 12", "A busca em largura usa fila.", 0.9, 0.8),
    TrechoRecuperado(9, "S2", "slide 3", "A busca em profundidade usa pilha.", 0.7, 0.6),
]


def test_formatar_trechos_prefixa_identificador_e_localizacao():
    assert formatar_trechos(TRECHOS) == (
        "[P1, página 12] A busca em largura usa fila.\n\n"
        "[S2, slide 3] A busca em profundidade usa pilha."
    )


def test_resolver_fontes_troca_identificador_por_id():
    fontes = [FonteGerada(identificador_material="S2", localizacao="slide 3", trecho_base="t")]
    assert resolver_fontes(fontes, TRECHOS) == [(9, "slide 3", "t")]


def test_fonte_inventada_e_rejeitada():
    """Sem esta checagem a rastreabilidade seria ficção."""
    fontes = [FonteGerada(identificador_material="P9", localizacao="x", trecho_base="t")]
    with pytest.raises(FonteInvalidaException) as capturado:
        resolver_fontes(fontes, TRECHOS)
    assert capturado.value.corpo()["identificador"] == "P9"
    assert capturado.value.corpo()["disponiveis"] == ["P1", "S2"]
