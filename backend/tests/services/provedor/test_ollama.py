import dataclasses
import json

import httpx
import pytest
from pydantic import BaseModel

from backend.app.exceptions import (
    FalhaTransporteLLMException,
    RespostaLLMInvalidaException,
)
from backend.app.services.provedor.ollama import ClienteOllama
from backend.app.services.provedor.tipos import ConfigLLM, RequisicaoLLM

CFG = ConfigLLM(
    base_url="http://ollama.invalido",
    num_ctx=8192,
    timeout_s=1.0,
    temperatura_padrao=0.3,
    max_tokens_padrao=2048,
)


class Questao(BaseModel):
    enunciado: str
    dificuldade: str


def cliente_com(responder) -> ClienteOllama:
    return ClienteOllama(
        provedor_id=7,
        modelo="qwen3:4b",
        base_url=CFG.base_url,
        cfg=CFG,
        cliente=httpx.Client(
            transport=httpx.MockTransport(responder), base_url=CFG.base_url
        ),
    )


def requisicao() -> RequisicaoLLM:
    return RequisicaoLLM(
        sistema="Você é um gerador de questões.",
        usuario="Gere uma questão sobre grafos.",
        formato=Questao,
    )


def resposta_ok(conteudo: dict, **extras) -> dict:
    corpo = {
        "message": {"role": "assistant", "content": json.dumps(conteudo)},
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 1200,
        "eval_count": 180,
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
    assert resposta.modelo == "qwen3:4b"


def test_num_ctx_e_schema_vao_no_corpo():
    vistos: list[dict] = []

    def responder(request: httpx.Request) -> httpx.Response:
        vistos.append(json.loads(request.content))
        return httpx.Response(
            200, json=resposta_ok({"enunciado": "x", "dificuldade": "facil"})
        )

    cliente_com(responder).gerar(requisicao())
    corpo = vistos[0]
    # Sem num_ctx explícito o Ollama usa 4096 e trunca o prompt em silêncio.
    assert corpo["options"]["num_ctx"] == 8192
    assert corpo["options"]["temperature"] == 0.3
    assert corpo["options"]["num_predict"] == 2048
    assert corpo["stream"] is False
    # Raciocínio desligado de propósito: os tokens de "thinking" do qwen3 são
    # descartados e estourariam num_predict numa questão completa.
    assert corpo["think"] is False
    assert corpo["format"]["properties"]["enunciado"]["type"] == "string"
    assert [m["role"] for m in corpo["messages"]] == ["system", "user"]


def test_temperatura_da_requisicao_sobrescreve_o_default():
    vistos: list[dict] = []

    def responder(request: httpx.Request) -> httpx.Response:
        vistos.append(json.loads(request.content))
        return httpx.Response(
            200, json=resposta_ok({"enunciado": "x", "dificuldade": "facil"})
        )

    req = RequisicaoLLM(
        sistema="s", usuario="u", formato=Questao, temperatura=0.0, max_tokens=64
    )
    cliente_com(responder).gerar(req)
    assert vistos[0]["options"]["temperature"] == 0.0
    assert vistos[0]["options"]["num_predict"] == 64


def test_done_reason_length_e_resposta_invalida_nao_falha_de_transporte():
    """Resposta cortada é JSON cortado. Trocar de provedor não conserta."""

    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=resposta_ok(
                {"enunciado": "x", "dificuldade": "facil"}, done_reason="length"
            ),
        )

    with pytest.raises(RespostaLLMInvalidaException, match="cortada"):
        cliente_com(responder).gerar(requisicao())


def test_conteudo_que_nao_e_json_e_resposta_invalida():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "desculpe, não consigo"},
                "done_reason": "stop",
            },
        )

    with pytest.raises(RespostaLLMInvalidaException, match="não é JSON"):
        cliente_com(responder).gerar(requisicao())


def test_json_valido_fora_do_schema_e_resposta_invalida():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=resposta_ok({"enunciado": "faltou campo"}))

    with pytest.raises(RespostaLLMInvalidaException, match="fora do schema"):
        cliente_com(responder).gerar(requisicao())


def test_resposta_sem_message_content_e_invalida():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"done_reason": "stop"})

    with pytest.raises(RespostaLLMInvalidaException, match="message.content"):
        cliente_com(responder).gerar(requisicao())


def test_erro_5xx_e_falha_de_transporte():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "modelo carregando"})

    with pytest.raises(FalhaTransporteLLMException, match="500"):
        cliente_com(responder).gerar(requisicao())


def test_modelo_ausente_404_e_falha_de_transporte_e_dispara_fallback():
    """404 = modelo não instalado neste provedor. Outro provedor pode ter."""

    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model not found"})

    with pytest.raises(FalhaTransporteLLMException, match="404"):
        cliente_com(responder).gerar(requisicao())


def test_erro_de_conexao_e_falha_de_transporte():
    def responder(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(FalhaTransporteLLMException, match="ConnectError"):
        cliente_com(responder).gerar(requisicao())


def test_contagem_de_tokens_ausente_nao_derruba_a_chamada():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"enunciado": "x", "dificuldade": "facil"}),
                },
                "done_reason": "stop",
            },
        )

    resposta = cliente_com(responder).gerar(requisicao())
    assert resposta.uso.entrada == 0
    assert resposta.uso.saida == 0


def test_cliente_http_cacheia_por_url_e_timeout():
    from backend.app.services.provedor.ollama import cliente_http

    base = "http://cache.invalido"
    assert cliente_http(base, 1.0) is cliente_http(base, 1.0)
    # Mesma URL, timeout diferente: clientes distintos — o timeout não pode
    # ser herdado do primeiro.
    assert cliente_http(base, 1.0) is not cliente_http(base, 2.0)


def test_resposta_cortada_diz_o_teto_e_as_variaveis_certas():
    """A mensagem apontava LLM_MAX_TOKENS_PADRAO, que geração, crítico e
    auditoria não usam."""

    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=resposta_ok(
                {"enunciado": "x", "dificuldade": "facil"}, done_reason="length"
            ),
        )

    req = dataclasses.replace(requisicao(), max_tokens=1024)
    with pytest.raises(RespostaLLMInvalidaException) as erro:
        cliente_com(responder).gerar(req)

    mensagem = str(erro.value)
    assert "1024" in mensagem
    assert "AUDITORIA_MAX_TOKENS" in mensagem
    assert "LLM_MAX_TOKENS_PADRAO" not in mensagem


def test_resposta_cortada_registra_o_final_no_log(caplog):
    """O final da resposta cortada é onde aparece a repetição que levou ao teto."""

    def responder(_request: httpx.Request) -> httpx.Response:
        corpo = resposta_ok({"enunciado": "x"}, done_reason="length")
        corpo["message"]["content"] = '{"fontes": [' + '{"a": 1}, ' * 200
        return httpx.Response(200, json=corpo)

    with pytest.raises(RespostaLLMInvalidaException):
        cliente_com(responder).gerar(requisicao())
    aviso = [r for r in caplog.records if "cortada" in r.getMessage()]
    assert len(aviso) == 1
    assert '{"a": 1}, ' in aviso[0].getMessage()
