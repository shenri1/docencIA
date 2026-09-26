def test_registrar_docente_retorna_201_sem_senha_hash(client):
    resp = client.post(
        "/auth/registrar",
        json={
            "nome": "Ana Souza",
            "credencial_institucional": "e2e001",
            "senha": "senhaforte123",
        },
    )
    assert resp.status_code == 201
    corpo = resp.json()
    assert corpo["credencial_institucional"] == "e2e001"
    assert "senha_hash" not in corpo
    assert "senha" not in corpo


def test_registrar_docente_com_credencial_duplicada_retorna_409(client):
    payload = {
        "nome": "Ana",
        "credencial_institucional": "e2e002",
        "senha": "senhaforte123",
    }
    client.post("/auth/registrar", json=payload)
    resp = client.post("/auth/registrar", json=payload)
    assert resp.status_code == 409


def test_login_com_credenciais_corretas_retorna_token(client):
    client.post(
        "/auth/registrar",
        json={
            "nome": "Ana",
            "credencial_institucional": "e2e003",
            "senha": "senhaforte123",
        },
    )
    resp = client.post(
        "/auth/login", data={"username": "e2e003", "password": "senhaforte123"}
    )
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"
    assert resp.json()["access_token"]


def test_login_com_senha_errada_retorna_401(client):
    client.post(
        "/auth/registrar",
        json={
            "nome": "Ana",
            "credencial_institucional": "e2e004",
            "senha": "senhaforte123",
        },
    )
    resp = client.post("/auth/login", data={"username": "e2e004", "password": "errada"})
    assert resp.status_code == 401


def test_me_sem_token_retorna_401(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_me_com_token_invalido_retorna_401(client):
    resp = client.get(
        "/auth/me", headers={"Authorization": "Bearer token.invalido.aqui"}
    )
    assert resp.status_code == 401


def test_me_com_token_valido_retorna_dados_do_docente(client):
    client.post(
        "/auth/registrar",
        json={
            "nome": "Ana",
            "credencial_institucional": "e2e005",
            "senha": "senhaforte123",
        },
    )
    login = client.post(
        "/auth/login", data={"username": "e2e005", "password": "senhaforte123"}
    )
    token = login.json()["access_token"]
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["credencial_institucional"] == "e2e005"


def test_entidades_de_auth_aparecem_documentadas_no_swagger(client):
    schema = client.get("/openapi.json").json()
    componentes = schema["components"]["schemas"]
    assert "DocenteResposta" in componentes
    assert "TokenResponse" in componentes
    assert "senha_hash" not in componentes["DocenteResposta"]["properties"]
