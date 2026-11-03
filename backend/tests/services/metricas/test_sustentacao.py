from types import SimpleNamespace

from backend.app.services.metricas.sustentacao import (
    medir_citacao,
    medir_sustentacao,
    normalizar,
)
from backend.app.services.rag.retrieval_service import TrechoRecuperado

TEXTO = (
    "A busca em largura percorre o grafo por níveis, usando uma fila para "
    "guardar os vértices a visitar. Cada vértice entra na fila uma única vez."
)


def _trecho(chunk_id: int, texto: str) -> TrechoRecuperado:
    return TrechoRecuperado(chunk_id, 1, "P1", "página 1", texto, 0.9, 0.8)


def test_normalizar_unifica_caixa_espacos_aspas_e_hifens():
    assert normalizar("  A “Fila”\n  é – FIFO  ") == 'a "fila" é - fifo'


def test_copia_literal():
    resultado = medir_citacao(
        "usando uma fila para guardar os vértices", [_trecho(4, TEXTO)]
    )
    assert resultado == {"literal": True, "similaridade": 1.0, "chunk_id": 4}


def test_espacos_e_maiusculas_continuam_literais():
    resultado = medir_citacao("USANDO  uma\nfila para guardar", [_trecho(4, TEXTO)])
    assert resultado["literal"] is True


def test_aspas_tipograficas_continuam_literais():
    trecho = _trecho(1, "o termo “fila” aparece aqui")
    assert medir_citacao('o termo "fila" aparece aqui', [trecho])["literal"] is True


def test_parafrase_fica_entre():
    resultado = medir_citacao(
        "a busca em largura visita o grafo por níveis e guarda os vértices numa fila",
        [_trecho(4, TEXTO)],
    )
    assert resultado["literal"] is False
    assert 0.4 < resultado["similaridade"] < 1.0


def test_texto_ausente_fica_baixo():
    resultado = medir_citacao(
        "o protocolo tcp estabelece conexão com handshake de três vias",
        [_trecho(4, TEXTO)],
    )
    assert resultado["literal"] is False
    assert resultado["similaridade"] < 0.4


def test_escolhe_o_trecho_de_melhor_casamento():
    outro = _trecho(
        9, "protocolo tcp com handshake de três vias entre cliente e servidor"
    )
    resultado = medir_citacao("handshake de três vias", [_trecho(4, TEXTO), outro])
    assert resultado["chunk_id"] == 9


def test_citacao_longa_com_uma_palavra_trocada_continua_alta():
    """Com 200+ caracteres o difflib ignoraria as letras comuns (autojunk) e a
    razão despencaria, embora quase tudo seja cópia."""
    original = (
        "A busca em largura percorre o grafo por níveis, usando uma fila para "
        "guardar os vértices a visitar. Cada vértice entra na fila uma única vez, "
        "e a distância até a origem cresce de um em um a cada nível percorrido pelo algoritmo."
    )
    citado = original.replace("percorrido", "visitado")
    assert len(citado) > 200
    resultado = medir_citacao(citado, [_trecho(4, original + " Fim do trecho.")])
    assert resultado["literal"] is False
    assert resultado["similaridade"] >= 0.95


def test_citacao_maior_que_o_trecho_nao_quebra():
    resultado = medir_citacao(TEXTO * 3, [_trecho(4, "fila")])
    assert resultado["literal"] is False
    assert 0.0 <= resultado["similaridade"] <= 1.0


def test_trecho_vazio_nao_quebra():
    resultado = medir_citacao("qualquer coisa", [_trecho(4, "")])
    assert resultado["literal"] is False
    assert resultado["similaridade"] == 0.0


def test_sem_trechos_devolve_chunk_none():
    assert medir_citacao("x", []) == {
        "literal": False,
        "similaridade": 0.0,
        "chunk_id": None,
    }


def test_medir_sustentacao_um_item_por_fonte():
    questao = SimpleNamespace(
        fontes_internas=[
            SimpleNamespace(
                id=11, material_id=1, localizacao="página 1", trecho_base="uma fila"
            ),
            SimpleNamespace(
                id=12, material_id=1, localizacao="página 2", trecho_base="inventado"
            ),
        ]
    )
    itens = medir_sustentacao(questao, [_trecho(4, TEXTO)])
    assert [i["fonte_id"] for i in itens] == [11, 12]
    assert itens[0]["literal"] is True and itens[0]["material_id"] == 1
    assert itens[1]["literal"] is False
