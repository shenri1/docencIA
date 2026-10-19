import json
import logging

import httpx
import pytest
from pydantic import BaseModel

from backend.app.exceptions import (
    FalhaTransporteLLMException,
    RespostaLLMInvalidaException,
)
from backend.app.services.provedor.llama_server import ClienteLlamaServer
from backend.app.services.provedor.tipos import ConfigLLM, RequisicaoLLM

CFG = ConfigLLM(
    base_url="http://llama.invalido",
    num_ctx=8192,
    timeout_s=1.0,
    temperatura_padrao=0.3,
    max_tokens_padrao=2048,
)


class Questao(BaseModel):
    enunciado: str
    dificuldade: str


def cliente_com(responder) -> ClienteLlamaServer:
    return ClienteLlamaServer(
        provedor_id=7,
        modelo="qwen3.5-9b",
        base_url=CFG.base_url,
        cfg=CFG,
        cliente=httpx.Client(
            transport=httpx.MockTransport(responder), base_url=CFG.base_url
        ),
    )


def requisicao(**extras) -> RequisicaoLLM:
    return RequisicaoLLM(
        sistema="Você é um gerador de questões.",
        usuario="Gere uma questão sobre grafos.",
        formato=Questao,
        **extras,
    )


def resposta_ok(conteudo: dict, finish_reason: str = "stop", **extras) -> dict:
    corpo = {
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": json.dumps(conteudo)},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 180},
    }
    corpo.update(extras)
    return corpo


def test_resposta_valida_vira_modelo_pydantic_e_uso():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=resposta_ok({"enunciado": "O que é BFS?", "dificuldade": "media"}),
        )

    resposta = cliente_com(responder).gerar(requisicao())
    assert isinstance(resposta.conteudo, Questao)
    assert resposta.conteudo.enunciado == "O que é BFS?"
    assert resposta.uso.entrada == 1200
    assert resposta.uso.saida == 180
    assert resposta.provedor_id == 7
    assert resposta.modelo == "qwen3.5-9b"


def test_corpo_usa_rota_openai_schema_e_raciocinio_desligado():
    vistos: list[tuple[str, dict]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        vistos.append((request.url.path, json.loads(request.content)))
        return httpx.Response(
            200, json=resposta_ok({"enunciado": "x", "dificuldade": "facil"})
        )

    cliente_com(responder).gerar(requisicao())
    caminho, corpo = vistos[0]
    assert caminho == "/v1/chat/completions"
    # O llama-swap roteia pelo campo model.
    assert corpo["model"] == "qwen3.5-9b"
    assert corpo["stream"] is False
    assert corpo["temperature"] == 0.3
    assert corpo["max_tokens"] == 2048
    assert corpo["response_format"]["type"] == "json_schema"
    schema = corpo["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["enunciado"]["type"] == "string"
    # Mesmo motivo do think:false do Ollama: tokens de raciocínio contam contra
    # o teto e são descartados.
    assert corpo["chat_template_kwargs"] == {"enable_thinking": False}
    assert [m["role"] for m in corpo["messages"]] == ["system", "user"]


def test_temperatura_e_teto_da_requisicao_sobrescrevem_o_default():
    vistos: list[dict] = []

    def responder(request: httpx.Request) -> httpx.Response:
        vistos.append(json.loads(request.content))
        return httpx.Response(
            200, json=resposta_ok({"enunciado": "x", "dificuldade": "facil"})
        )

    cliente_com(responder).gerar(requisicao(temperatura=0.0, max_tokens=64))
    assert vistos[0]["temperature"] == 0.0
    assert vistos[0]["max_tokens"] == 64


def test_finish_reason_length_e_resposta_invalida_e_diz_o_teto():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=resposta_ok(
                {"enunciado": "x", "dificuldade": "facil"}, finish_reason="length"
            ),
        )

    with pytest.raises(RespostaLLMInvalidaException) as erro:
        cliente_com(responder).gerar(requisicao(max_tokens=1024))
    assert "1024" in str(erro.value)
    assert "AUDITORIA_MAX_TOKENS" in str(erro.value)


def test_conteudo_que_nao_e_json_e_resposta_invalida():
    def responder(_request: httpx.Request) -> httpx.Response:
        corpo = resposta_ok({})
        corpo["choices"][0]["message"]["content"] = "desculpe, não consigo"
        return httpx.Response(200, json=corpo)

    with pytest.raises(RespostaLLMInvalidaException, match="não é JSON"):
        cliente_com(responder).gerar(requisicao())


def test_json_fora_do_schema_e_resposta_invalida():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=resposta_ok({"enunciado": "faltou campo"}))

    with pytest.raises(RespostaLLMInvalidaException, match="fora do schema"):
        cliente_com(responder).gerar(requisicao())


def test_resposta_sem_choices_e_invalida():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    with pytest.raises(RespostaLLMInvalidaException, match="message.content"):
        cliente_com(responder).gerar(requisicao())


@pytest.mark.parametrize("status", [404, 500, 503])
def test_erro_http_e_falha_de_transporte(status):
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "x"})

    with pytest.raises(FalhaTransporteLLMException, match=str(status)):
        cliente_com(responder).gerar(requisicao())


def test_erro_de_conexao_e_falha_de_transporte():
    def responder(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(FalhaTransporteLLMException, match="ConnectError"):
        cliente_com(responder).gerar(requisicao())


def test_usage_ausente_nao_derruba_a_chamada():
    def responder(_request: httpx.Request) -> httpx.Response:
        corpo = resposta_ok({"enunciado": "x", "dificuldade": "facil"})
        del corpo["usage"]
        return httpx.Response(200, json=corpo)

    resposta = cliente_com(responder).gerar(requisicao())
    assert (resposta.uso.entrada, resposta.uso.saida) == (0, 0)


def test_timings_do_servidor_vao_para_o_log(caplog):
    """É a razão de existir deste cliente: tokens/s medido pelo servidor."""

    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=resposta_ok(
                {"enunciado": "x", "dificuldade": "facil"},
                timings={
                    "prompt_n": 1200,
                    "prompt_ms": 800.5,
                    "prompt_per_second": 1499.1,
                    "predicted_n": 180,
                    "predicted_ms": 9000.0,
                    "predicted_per_second": 20.0,
                },
            ),
        )

    with caplog.at_level(logging.INFO, logger="docencia.llm.metricas"):
        cliente_com(responder).gerar(requisicao())

    registro = next(r for r in caplog.records if r.name == "docencia.llm.metricas")
    assert registro.modelo == "qwen3.5-9b"
    assert registro.timings["predicted_per_second"] == 20.0
