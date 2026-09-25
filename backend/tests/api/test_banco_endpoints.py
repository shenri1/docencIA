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
