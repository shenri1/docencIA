import math

import httpx
import pytest

from backend.app.exceptions import FalhaRerankException
from backend.app.services.rag import rerank as mod
from backend.app.services.rag.rerank import (
    ConfigRerank,
    RerankerFake,
    RerankerOllamaLogprobs,
)

CFG = ConfigRerank(
    base_url="http://ollama.invalido",
    modelo="dengcao/Qwen3-Reranker-0.6B:F16",
    instrucao="Retrieve passages",
    timeout_s=1.0,
)


def cliente_com(resposta):
    return httpx.Client(transport=httpx.MockTransport(resposta), base_url=CFG.base_url)


def resposta_logprobs(lp_sim: float, lp_nao: float) -> dict:
    return {
        "response": "yes",
        "logprobs": [
            {
                "token": "yes",
                "logprob": lp_sim,
                "top_logprobs": [
                    {"token": "yes", "logprob": lp_sim},
                    {"token": "no", "logprob": lp_nao},
                ],
            }
        ],
    }


def test_score_vem_do_softmax_entre_yes_e_no():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=resposta_logprobs(-0.1, -2.3))

    reranker = RerankerOllamaLogprobs(CFG, cliente=cliente_com(responder))
    [(indice, score)] = reranker.reordenar("pergunta", ["documento"], top_n=5)
    esperado = math.exp(-0.1) / (math.exp(-0.1) + math.exp(-2.3))
    assert indice == 0
    assert score == pytest.approx(esperado)


def test_ordem_final_e_por_score_decrescente():
    scores = iter([(-3.0, -0.1), (-0.1, -3.0), (-1.0, -1.0)])

    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=resposta_logprobs(*next(scores)))

    reranker = RerankerOllamaLogprobs(CFG, cliente=cliente_com(responder))
    resultado = reranker.reordenar("q", ["a", "b", "c"], top_n=3)
    assert [indice for indice, _ in resultado] == [1, 2, 0]


def test_top_n_limita_a_saida():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=resposta_logprobs(-0.5, -1.5))

    reranker = RerankerOllamaLogprobs(CFG, cliente=cliente_com(responder))
    assert len(reranker.reordenar("q", ["a", "b", "c", "d"], top_n=2)) == 2


def test_token_com_espaco_e_maiuscula_casa():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "logprobs": [
                    {
                        "token": " Yes",
                        "logprob": -0.2,
                        "top_logprobs": [
                            {"token": " Yes", "logprob": -0.2},
                            {"token": " No", "logprob": -1.9},
                        ],
                    }
                ]
            },
        )

    reranker = RerankerOllamaLogprobs(CFG, cliente=cliente_com(responder))
    [(_, score)] = reranker.reordenar("q", ["a"], top_n=1)
    assert score > 0.5


def test_par_indeciso_recebe_score_zero_mas_nao_derruba_a_busca():
    respostas = iter(
        [
            {
                "logprobs": [
                    {
                        "token": "talvez",
                        "top_logprobs": [{"token": "talvez", "logprob": -0.1}],
                    }
                ]
            },
            resposta_logprobs(-0.1, -3.0),
        ]
    )

    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(respostas))

    reranker = RerankerOllamaLogprobs(CFG, cliente=cliente_com(responder))
    resultado = reranker.reordenar("q", ["a", "b"], top_n=2)
    assert resultado[0][0] == 1
    assert resultado[1] == (0, 0.0)


def test_todos_indecisos_falha_alto():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"logprobs": []})

    reranker = RerankerOllamaLogprobs(CFG, cliente=cliente_com(responder))
    with pytest.raises(FalhaRerankException, match="0.12.11"):
        reranker.reordenar("q", ["a", "b"], top_n=2)


def test_erro_de_rede_falha(monkeypatch):
    monkeypatch.setattr(mod, "_BACKOFF_BASE_S", 0.0)

    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "modelo carregando"})

    reranker = RerankerOllamaLogprobs(CFG, cliente=cliente_com(responder))
    with pytest.raises(FalhaRerankException):
        reranker.reordenar("q", ["a"], top_n=1)


def test_lista_vazia_nao_chama_o_modelo_nem_falha():
    def responder(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("não deveria chamar o modelo")

    reranker = RerankerOllamaLogprobs(CFG, cliente=cliente_com(responder))
    assert reranker.reordenar("q", [], top_n=5) == []


def test_prompt_traz_consulta_documento_e_instrucao():
    vistos: list[str] = []

    def responder(request: httpx.Request) -> httpx.Response:
        import json

        vistos.append(json.loads(request.content)["prompt"])
        return httpx.Response(200, json=resposta_logprobs(-0.1, -2.0))

    reranker = RerankerOllamaLogprobs(CFG, cliente=cliente_com(responder))
    reranker.reordenar("minha pergunta", ["meu documento"], top_n=1)
    assert "<Query>: minha pergunta" in vistos[0]
    assert "<Document>: meu documento" in vistos[0]
    assert "<Instruct>: Retrieve passages" in vistos[0]


def test_fake_preserva_a_ordem_de_entrada():
    assert RerankerFake().reordenar("q", ["a", "b", "c"], top_n=2) == [
        (0, 1.0),
        (1, 0.5),
    ]


def test_get_reranker_reusa_o_mesmo_cliente():
    """Dependência é singleton: um httpx.Client por processo, não por request."""
    assert mod.get_reranker() is mod.get_reranker()


def test_token_amostrado_fora_do_top_logprobs_ainda_conta():
    """O token escolhido ("yes") pode não ser repetido em top_logprobs — ele
    vem do campo token/logprob de primeira ordem e não pode virar score 0."""

    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "logprobs": [
                    {
                        "token": "yes",
                        "logprob": -0.1,
                        "top_logprobs": [{"token": "no", "logprob": -3.0}],
                    }
                ]
            },
        )

    reranker = RerankerOllamaLogprobs(CFG, cliente=cliente_com(responder))
    [(_, score)] = reranker.reordenar("q", ["a"], top_n=1)
    esperado = math.exp(-0.1) / (math.exp(-0.1) + math.exp(-3.0))
    assert score == pytest.approx(esperado)


def test_distribuicao_uniforme_aponta_o_modelo():
    """Regressão: o GGUF dengcao/Qwen3-Reranker devolve, pelo /api/generate, o
    mesmo logprob (-ln do vocabulário) para todo token. Não é template nem
    versão do Ollama: o modelo não está gerando texto."""
    uniforme = -math.log(151_669)

    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": "3",
                "logprobs": [
                    {
                        "token": "3",
                        "logprob": uniforme,
                        "top_logprobs": [
                            {"token": t, "logprob": uniforme} for t in "3+%1-)4"
                        ],
                    }
                ],
            },
        )

    reranker = RerankerOllamaLogprobs(CFG, cliente=cliente_com(responder))
    with pytest.raises(FalhaRerankException, match="uniforme") as erro:
        reranker.reordenar("q", ["a", "b"], top_n=2)
    assert CFG.modelo in str(erro.value)
