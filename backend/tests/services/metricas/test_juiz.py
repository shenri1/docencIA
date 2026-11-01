import json

import httpx
import pytest

from backend.app.services.metricas.juiz import (
    VERSAO_PROMPT_JUIZ,
    ConfigJuiz,
    FalhaJuizException,
    JuizFake,
    JuizOllama,
)

CFG = ConfigJuiz(
    base_url="http://juiz.test", modelo="qwen3:4b", timeout_s=5.0, max_tokens=256
)

OK = {
    "message": {
        "content": json.dumps(
            {"nota_tema": 4, "nota_trecho": 3, "justificativa": "cobre o tema"}
        )
    },
    "prompt_eval_count": 120,
    "eval_count": 30,
}


def _juiz(manipulador) -> tuple[JuizOllama, list[httpx.Request]]:
    vistas: list[httpx.Request] = []

    def passo(requisicao: httpx.Request) -> httpx.Response:
        vistas.append(requisicao)
        return manipulador(requisicao)

    cliente = httpx.Client(base_url=CFG.base_url, transport=httpx.MockTransport(passo))
    return JuizOllama(CFG, cliente), vistas


def _avaliar(juiz: JuizOllama):
    return juiz.avaliar("grafos", "Qual estrutura a BFS usa?", ["BFS usa fila.", "x"])


def test_corpo_da_requisicao():
    juiz, vistas = _juiz(lambda r: httpx.Response(200, json=OK))
    _avaliar(juiz)
    corpo = json.loads(vistas[0].content)
    assert vistas[0].url.path == "/api/chat"
    assert corpo["model"] == "qwen3:4b"
    assert corpo["think"] is False
    assert corpo["stream"] is False
    assert corpo["options"]["num_gpu"] == 0
    assert corpo["options"]["temperature"] == 0
    assert "nota_tema" in corpo["format"]["properties"]


def test_resposta_valida_vira_resultado():
    juiz, _ = _juiz(lambda r: httpx.Response(200, json=OK))
    r = _avaliar(juiz)
    assert (r.avaliacao.nota_tema, r.avaliacao.nota_trecho) == (4, 3)
    assert (r.uso.entrada, r.uso.saida) == (120, 30)
    assert r.modelo == "qwen3:4b"
    assert r.versao_prompt == VERSAO_PROMPT_JUIZ
    assert r.versao_prompt.startswith("aderencia@")


def test_trechos_vao_numerados_no_usuario():
    juiz, vistas = _juiz(lambda r: httpx.Response(200, json=OK))
    _avaliar(juiz)
    usuario = json.loads(vistas[0].content)["messages"][1]["content"]
    assert "grafos" in usuario and "Qual estrutura a BFS usa?" in usuario
    assert "[1] BFS usa fila." in usuario and "[2] x" in usuario


def test_nota_fora_de_1_a_5_vira_falha():
    ruim = {
        **OK,
        "message": {
            "content": json.dumps(
                {"nota_tema": 6, "nota_trecho": 3, "justificativa": "x"}
            )
        },
    }
    juiz, _ = _juiz(lambda r: httpx.Response(200, json=ruim))
    with pytest.raises(FalhaJuizException):
        _avaliar(juiz)


def test_http_500_vira_falha():
    juiz, _ = _juiz(lambda r: httpx.Response(500))
    with pytest.raises(FalhaJuizException, match="HTTP 500"):
        _avaliar(juiz)


def test_timeout_vira_falha():
    def estoura(_):
        raise httpx.ReadTimeout("lento")

    juiz, _ = _juiz(estoura)
    with pytest.raises(FalhaJuizException, match="ReadTimeout"):
        _avaliar(juiz)


def test_json_quebrado_vira_falha():
    quebrado = {**OK, "message": {"content": "{nao e json"}}
    juiz, _ = _juiz(lambda r: httpx.Response(200, json=quebrado))
    with pytest.raises(FalhaJuizException):
        _avaliar(juiz)


def test_fake_padrao_e_registra_chamadas():
    fake = JuizFake()
    r = fake.avaliar("tema", "questão", ["t1"])
    assert (r.avaliacao.nota_tema, r.avaliacao.nota_trecho) == (5, 5)
    assert fake.chamadas == [("tema", "questão", ["t1"])]


def test_fake_com_excecao_levanta():
    fake = JuizFake(FalhaJuizException("timeout"))
    with pytest.raises(FalhaJuizException, match="timeout"):
        fake.avaliar("t", "q", [])
