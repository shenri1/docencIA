def test_gerar_banco_sem_token_e_401(client):
    assert (
        client.post("/sessoes/1/banco", json={"n_alvo": 5, "versao": "v1"}).status_code
        == 401
    )


def test_n_alvo_fora_da_faixa_e_422(client):
    from backend.tests.api.test_rag_endpoints import _auth

    cabecalhos = _auth(client, "banco001")
    resposta = client.post(
        "/sessoes/1/banco", json={"n_alvo": 0, "versao": "v1"}, headers=cabecalhos
    )
    assert resposta.status_code == 422


def test_sessao_de_outro_docente_e_404(client):
    from backend.tests.api.test_rag_endpoints import _auth

    cabecalhos = _auth(client, "banco002")
    resposta = client.post(
        "/sessoes/999999/banco", json={"n_alvo": 5, "versao": "v1"}, headers=cabecalhos
    )
    assert resposta.status_code == 404


def test_rota_de_banco_esta_no_swagger(client):
    schema = client.get("/openapi.json").json()
    assert "/sessoes/{sessao_id}/banco" in schema["paths"]
    assert "ResumoBancoResposta" in schema["components"]["schemas"]


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
