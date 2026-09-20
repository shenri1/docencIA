import httpx
import pytest

from backend.app.exceptions import (
    ConfiguracaoEmbeddingInvalidaException,
    FalhaEmbeddingException,
)
from backend.app.services.rag import embeddings as mod
from backend.app.services.rag.embeddings import (
    ConfigEmbeddings,
    EmbeddingsFake,
    EmbeddingsOllama,
)

CFG = ConfigEmbeddings(
    base_url="http://ollama.invalido",
    modelo="qwen3-embedding:0.6b",
    instrucao_consulta="Retrieve passages",
    instrucao_documento="",
    lote=2,
    timeout_s=1.0,
    dimensao=4,
)


def cliente_com(resposta):
    transporte = httpx.MockTransport(resposta)
    return httpx.Client(transport=transporte, base_url=CFG.base_url)


def test_embutir_documentos_devolve_um_vetor_por_texto():
    def responder(request: httpx.Request) -> httpx.Response:
        import json

        entrada = json.loads(request.content)["input"]
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "embedding": [1.0, 0.0, 0.0, 0.0]}
                    for i in range(len(entrada))
                ]
            },
        )

    cliente = EmbeddingsOllama(CFG, cliente=cliente_com(responder))
    vetores = cliente.embutir_documentos(["a", "b", "c"])
    assert len(vetores) == 3


def test_vetores_sao_reordenados_pelo_campo_index():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 2.0, 0.0, 0.0]},
                    {"index": 0, "embedding": [2.0, 0.0, 0.0, 0.0]},
                ]
            },
        )

    cliente = EmbeddingsOllama(CFG, cliente=cliente_com(responder))
    primeiro, segundo = cliente.embutir_documentos(["a", "b"])
    assert primeiro[0] == pytest.approx(1.0)
    assert segundo[1] == pytest.approx(1.0)


def test_vetor_sai_normalizado():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [3.0, 4.0, 0.0, 0.0]}]}
        )

    cliente = EmbeddingsOllama(CFG, cliente=cliente_com(responder))
    vetor = cliente.embutir_consulta("consulta")
    assert sum(v * v for v in vetor) == pytest.approx(1.0)
    assert vetor[0] == pytest.approx(0.6)


def test_dimensao_errada_e_erro_de_configuracao():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})

    cliente = EmbeddingsOllama(CFG, cliente=cliente_com(responder))
    with pytest.raises(ConfiguracaoEmbeddingInvalidaException):
        cliente.embutir_consulta("consulta")


def test_quantidade_de_vetores_divergente_e_falha():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [1.0, 0.0, 0.0, 0.0]}]}
        )

    cliente = EmbeddingsOllama(CFG, cliente=cliente_com(responder))
    with pytest.raises(FalhaEmbeddingException):
        cliente.embutir_documentos(["a", "b"])


def test_erro_5xx_retenta_e_depois_falha(monkeypatch):
    monkeypatch.setattr(mod, "_BACKOFF_BASE_S", 0.0)
    chamadas = {"n": 0}

    def responder(_request: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        return httpx.Response(500, json={"error": "modelo carregando"})

    cliente = EmbeddingsOllama(CFG, cliente=cliente_com(responder))
    with pytest.raises(FalhaEmbeddingException):
        cliente.embutir_consulta("consulta")
    assert chamadas["n"] == mod._TENTATIVAS


def test_erro_5xx_seguido_de_sucesso_passa(monkeypatch):
    monkeypatch.setattr(mod, "_BACKOFF_BASE_S", 0.0)
    chamadas = {"n": 0}

    def responder(_request: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            return httpx.Response(503, json={"error": "indisponível"})
        return httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [1.0, 0.0, 0.0, 0.0]}]}
        )

    cliente = EmbeddingsOllama(CFG, cliente=cliente_com(responder))
    assert cliente.embutir_consulta("consulta")[0] == pytest.approx(1.0)


def test_instrucao_so_e_aplicada_na_consulta():
    vistos: list[str] = []

    def responder(request: httpx.Request) -> httpx.Response:
        import json

        vistos.extend(json.loads(request.content)["input"])
        return httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [1.0, 0.0, 0.0, 0.0]}]}
        )

    cliente = EmbeddingsOllama(CFG, cliente=cliente_com(responder))
    cliente.embutir_consulta("minha pergunta")
    cliente.embutir_documentos(["meu documento"])
    assert vistos[0] == "Instruct: Retrieve passages\nQuery: minha pergunta"
    assert vistos[1] == "meu documento"


def test_lote_parte_a_chamada():
    lotes: list[int] = []

    def responder(request: httpx.Request) -> httpx.Response:
        import json

        entrada = json.loads(request.content)["input"]
        lotes.append(len(entrada))
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "embedding": [1.0, 0.0, 0.0, 0.0]}
                    for i in range(len(entrada))
                ]
            },
        )

    cliente = EmbeddingsOllama(CFG, cliente=cliente_com(responder))
    cliente.embutir_documentos(["a", "b", "c", "d", "e"])
    assert lotes == [2, 2, 1]


def test_fake_e_deterministico_e_normalizado():
    fake = EmbeddingsFake(dimensao=16)
    assert fake.embutir_consulta("texto") == fake.embutir_consulta("texto")
    assert fake.embutir_consulta("a") != fake.embutir_consulta("b")
    assert sum(v * v for v in fake.embutir_consulta("texto")) == pytest.approx(1.0)


def test_get_embeddings_reusa_o_mesmo_cliente():
    """Dependência é singleton: um httpx.Client por processo, não por request."""
    assert mod.get_embeddings() is mod.get_embeddings()


def test_resposta_sem_index_falha():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"data": [{"embedding": [1.0, 0.0, 0.0, 0.0]}]}
        )

    cliente = EmbeddingsOllama(CFG, cliente=cliente_com(responder))
    with pytest.raises(FalhaEmbeddingException):
        cliente.embutir_consulta("consulta")


def test_vetor_nulo_do_modelo_falha():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [0.0, 0.0, 0.0, 0.0]}]}
        )

    cliente = EmbeddingsOllama(CFG, cliente=cliente_com(responder))
    with pytest.raises(FalhaEmbeddingException):
        cliente.embutir_consulta("consulta")
