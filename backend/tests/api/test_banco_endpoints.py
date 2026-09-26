import pytest

from backend.tests.conftest import _auth


def test_gerar_banco_sem_token_e_401(client):
    assert (
        client.post(
            "/sessoes/1/banco",
            json={"n_objetivas": 5, "n_discursivas": 0, "versao": "v1"},
        ).status_code
        == 401
    )


def test_soma_zero_e_422(client):
    cabecalhos = _auth(client, "banco001")
    resposta = client.post(
        "/sessoes/1/banco",
        json={"n_objetivas": 0, "n_discursivas": 0, "versao": "v1"},
        headers=cabecalhos,
    )
    assert resposta.status_code == 422


def test_sessao_de_outro_docente_e_404(client):
    cabecalhos = _auth(client, "banco002")
    resposta = client.post(
        "/sessoes/999999/banco",
        json={"n_objetivas": 5, "n_discursivas": 0, "versao": "v1"},
        headers=cabecalhos,
    )
    assert resposta.status_code == 404


def test_resumo_expoe_violacoes_e_nunca_o_rascunho(client):
    schema = client.get("/openapi.json").json()
    componentes = schema["components"]["schemas"]
    assert "com_violacoes" in componentes["ResumoBancoResposta"]["properties"]
    assert set(componentes["ViolacaoResposta"]["properties"]) == {
        "regra",
        "alvo",
        "detalhe",
    }
    # O rascunho é dado de pesquisa, nunca payload do docente. Checa
    # a chave de propriedade, não substring: EstadoSessao.RASCUNHO já é um
    # valor de enum legítimo e apareceria numa checagem ingênua de substring.
    assert not any(
        "rascunho" in schema_obj.get("properties", {})
        for schema_obj in componentes.values()
    )


@pytest.mark.parametrize(
    ("n_obj", "n_disc", "status"),
    [(17, 8, 404), (25, 0, 404), (0, 25, 404), (17, 9, 422), (26, 0, 422), (0, 0, 422)],
)
def test_limite_de_25_somando_os_dois_tipos(client, n_obj, n_disc, status):
    """404 = passou da validação e esbarrou na sessão inexistente; 422 = barrado
    pelo schema, antes de qualquer serviço."""
    cabecalhos = _auth(client, f"banco25{n_obj}{n_disc}")
    resposta = client.post(
        "/sessoes/999999/banco",
        json={"n_objetivas": n_obj, "n_discursivas": n_disc, "versao": "v1"},
        headers=cabecalhos,
    )
    assert resposta.status_code == status


def test_resumo_expoe_geradas_por_tipo(client):
    componentes = client.get("/openapi.json").json()["components"]["schemas"]
    assert "geradas_por_tipo" in componentes["ResumoBancoResposta"]["properties"]
