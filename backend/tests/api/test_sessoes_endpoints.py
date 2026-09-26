PAYLOAD = {
    "disciplina": "Cálculo I",
    "periodo": "2026.2",
    "k_alternativas": 5,
    "p_f": 30,
    "p_m": 40,
    "p_d": 30,
}


def _token(client) -> str:
    client.post(
        "/auth/registrar",
        json={
            "nome": "Ana",
            "credencial_institucional": "sess001",
            "senha": "senhaforte123",
        },
    )
    login = client.post(
        "/auth/login", data={"username": "sess001", "password": "senhaforte123"}
    )
    return login.json()["access_token"]


def _auth(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(client)}"}


def test_criar_sessao_retorna_201(client):
    resp = client.post("/sessoes", json=PAYLOAD, headers=_auth(client))
    assert resp.status_code == 201
    corpo = resp.json()
    assert corpo["estado"] == "rascunho"
    assert corpo["disciplina"] == "Cálculo I"
    assert "docente_id" not in corpo


def test_criar_sessao_sem_token_retorna_401(client):
    resp = client.post("/sessoes", json=PAYLOAD)
    assert resp.status_code == 401


def test_criar_sessao_com_distribuicao_invalida_retorna_422(client):
    payload = PAYLOAD | {"p_d": 40}
    resp = client.post("/sessoes", json=payload, headers=_auth(client))
    assert resp.status_code == 422
    assert resp.json()["codigo"] == "PARAMETROS_INCONSISTENTES"


def test_listar_e_obter_sessao_do_proprio_docente(client):
    cabecalhos = _auth(client)
    criada = client.post("/sessoes", json=PAYLOAD, headers=cabecalhos).json()

    listagem = client.get("/sessoes", headers=cabecalhos)
    assert listagem.status_code == 200
    assert [s["id"] for s in listagem.json()] == [criada["id"]]

    detalhe = client.get(f"/sessoes/{criada['id']}", headers=cabecalhos)
    assert detalhe.status_code == 200
    assert detalhe.json()["id"] == criada["id"]


def test_obter_sessao_inexistente_retorna_404(client):
    resp = client.get("/sessoes/9999", headers=_auth(client))
    assert resp.status_code == 404
    assert resp.json()["codigo"] == "SESSAO_NAO_ENCONTRADA"
