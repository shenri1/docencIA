from types import SimpleNamespace

from backend.app.services.geracao import busca_orientada
from backend.app.services.geracao.busca_orientada import trechos_com_orientacoes
from backend.app.services.rag.retrieval_service import TrechoRecuperado

ANCORA = SimpleNamespace(texto="fila na busca em largura")


def _trecho(localizacao: str, texto: str | None = None) -> TrechoRecuperado:
    return TrechoRecuperado(
        material_id=1,
        identificador_curto="P1",
        localizacao=localizacao,
        texto=texto or f"texto de {localizacao}",
        score=1.0,
        score_vetorial=1.0,
    )


def _orientacao(cruzar_com=None, o_que_mudar=None):
    return SimpleNamespace(cruzar_com=cruzar_com, o_que_mudar=o_que_mudar)


class BuscaFalsa:
    """Responde por consulta e registra (consulta, k, candidatos)."""

    def __init__(self, respostas: dict[str, list[TrechoRecuperado]]) -> None:
        self.respostas = respostas
        self.chamadas: list[tuple[str, int, int]] = []

    def __call__(self, db, embeddings, reranker, sessao, consulta, k, candidatos):
        self.chamadas.append((consulta, k, candidatos))
        return list(self.respostas[consulta])


def _instalar(monkeypatch, respostas) -> BuscaFalsa:
    falsa = BuscaFalsa(respostas)
    monkeypatch.setattr(busca_orientada, "buscar", falsa)
    return falsa


def test_sem_cruzamento_e_exatamente_a_busca_da_ancora(monkeypatch):
    da_ancora = [_trecho(f"página {i}") for i in range(8)]
    falsa = _instalar(monkeypatch, {ANCORA.texto: da_ancora})

    trechos = trechos_com_orientacoes(
        None, None, None, None, ANCORA, [_orientacao(o_que_mudar="enunciado curto")]
    )

    assert trechos == da_ancora
    assert falsa.chamadas == [(ANCORA.texto, 8, 20)]


def test_cada_cruzamento_consulta_assunto_e_ancora(monkeypatch):
    arquitetura = f"arquitetura de computadores\n{ANCORA.texto}"
    cache = f"memória cache\n{ANCORA.texto}"
    falsa = _instalar(
        monkeypatch,
        {
            ANCORA.texto: [_trecho(f"página {i}") for i in range(8)],
            arquitetura: [_trecho(f"arq {i}") for i in range(3)],
            cache: [_trecho(f"cache {i}") for i in range(3)],
        },
    )

    trechos = trechos_com_orientacoes(
        None,
        None,
        None,
        None,
        ANCORA,
        [
            _orientacao(cruzar_com="arquitetura de computadores"),
            _orientacao(o_que_mudar="exemplos práticos"),
            _orientacao(cruzar_com="memória cache"),
        ],
    )

    assert falsa.chamadas == [(ANCORA.texto, 8, 20), (arquitetura, 3, 10), (cache, 3, 10)]
    assert len(trechos) == 14
    assert [t.localizacao for t in trechos[8:]] == [
        "arq 0", "arq 1", "arq 2", "cache 0", "cache 1", "cache 2",
    ]


def test_repetido_fica_na_primeira_ocorrencia(monkeypatch):
    redes = f"redes\n{ANCORA.texto}"
    _instalar(
        monkeypatch,
        {
            ANCORA.texto: [_trecho("página 1"), _trecho("página 2")],
            redes: [_trecho("página 2"), _trecho("página 9")],
        },
    )

    trechos = trechos_com_orientacoes(
        None, None, None, None, ANCORA, [_orientacao(cruzar_com="redes")]
    )

    assert [t.localizacao for t in trechos] == ["página 1", "página 2", "página 9"]


def test_mesma_pagina_com_textos_diferentes_nao_e_repetido(monkeypatch):
    """O chunking divide um bloco longo em pedaços com a mesma localização."""
    redes = f"redes\n{ANCORA.texto}"
    _instalar(
        monkeypatch,
        {
            ANCORA.texto: [_trecho("página 3", "primeira metade")],
            redes: [_trecho("página 3", "segunda metade")],
        },
    )

    trechos = trechos_com_orientacoes(
        None, None, None, None, ANCORA, [_orientacao(cruzar_com="redes")]
    )

    assert [t.texto for t in trechos] == ["primeira metade", "segunda metade"]
