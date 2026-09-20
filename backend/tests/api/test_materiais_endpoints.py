from backend.tests.fabricas import pdf_com_texto, pdf_protegido, txt_bytes

PDF = pdf_com_texto(["Conteúdo suficiente da primeira página para o limiar."])
SESSAO = {
    "disciplina": "Cálculo I",
    "periodo": "2026.2",
    "k_alternativas": 5,
    "p_f": 30,
    "p_m": 40,
    "p_d": 30,
}


def _auth(client, credencial="mat001") -> dict[str, str]:
    client.post(
        "/auth/registrar",
        json={
            "nome": "Ana",
            "credencial_institucional": credencial,
            "senha": "senhaforte123",
        },
    )
    login = client.post(
        "/auth/login", data={"username": credencial, "password": "senhaforte123"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _sessao(client, cabecalhos) -> int:
    return client.post("/sessoes", json=SESSAO, headers=cabecalhos).json()["id"]


def _enviar(client, cabecalhos, sessao_id, dados=PDF, nome="aula.pdf", tipo="pdf"):
    return client.post(
        f"/sessoes/{sessao_id}/materiais",
        headers=cabecalhos,
        files={"arquivo": (nome, dados, "application/pdf")},
        data={"tipo": tipo},
    )


def test_upload_retorna_201_sem_vazar_dados_internos(client):
    cabecalhos = _auth(client)
    sessao_id = _sessao(client, cabecalhos)
    resp = _enviar(client, cabecalhos, sessao_id)
    assert resp.status_code == 201
    corpo = resp.json()
    assert corpo["identificador_curto"] == "P1"
    assert corpo["formato"] == "pdf"
    assert corpo["contagem_paginas_logicas"] == 1
    for proibido in ("chave_armazenamento", "chave_texto_extraido", "hash_sha256"):
        assert proibido not in corpo


def test_upload_sem_token_retorna_401(client):
    cabecalhos = _auth(client)
    sessao_id = _sessao(client, cabecalhos)
    resp = client.post(
        f"/sessoes/{sessao_id}/materiais",
        files={"arquivo": ("aula.pdf", PDF, "application/pdf")},
        data={"tipo": "pdf"},
    )
    assert resp.status_code == 401


def test_upload_em_sessao_de_outro_docente_retorna_404(client):
    dono = _auth(client, "dono001")
    sessao_id = _sessao(client, dono)
    intruso = _auth(client, "intruso001")
    resp = _enviar(client, intruso, sessao_id)
    assert resp.status_code == 404
    assert resp.json()["codigo"] == "SESSAO_NAO_ENCONTRADA"


def test_upload_de_pdf_protegido_retorna_422_descritivo(client):
    cabecalhos = _auth(client)
    sessao_id = _sessao(client, cabecalhos)
    resp = _enviar(client, cabecalhos, sessao_id, dados=pdf_protegido())
    assert resp.status_code == 422
    corpo = resp.json()
    assert corpo["codigo"] == "PDF_PROTEGIDO"
    assert corpo["motivo"]
    assert corpo["detail"]


def test_upload_de_formato_nao_suportado_retorna_415(client):
    cabecalhos = _auth(client)
    sessao_id = _sessao(client, cabecalhos)
    resp = client.post(
        f"/sessoes/{sessao_id}/materiais",
        headers=cabecalhos,
        files={
            "arquivo": (
                "planilha.xlsx",
                b"PK\x03\x04qualquer",
                "application/vnd.ms-excel",
            )
        },
        data={"tipo": "livro"},
    )
    assert resp.status_code == 415
    assert resp.json()["codigo"] == "FORMATO_NAO_SUPORTADO"


def test_upload_duplicado_retorna_409(client):
    cabecalhos = _auth(client)
    sessao_id = _sessao(client, cabecalhos)
    _enviar(client, cabecalhos, sessao_id)
    resp = _enviar(client, cabecalhos, sessao_id, nome="copia.pdf")
    assert resp.status_code == 409
    assert resp.json()["codigo"] == "MATERIAL_DUPLICADO"


def test_indice_lista_materiais_e_estado_de_confirmacao(client):
    cabecalhos = _auth(client)
    sessao_id = _sessao(client, cabecalhos)
    _enviar(client, cabecalhos, sessao_id)
    resp = client.get(f"/sessoes/{sessao_id}/materiais/indice", headers=cabecalhos)
    assert resp.status_code == 200
    assert resp.json()["confirmado"] is False
    assert len(resp.json()["materiais"]) == 1


def test_remover_material_retorna_204(client):
    cabecalhos = _auth(client)
    sessao_id = _sessao(client, cabecalhos)
    material_id = _enviar(client, cabecalhos, sessao_id).json()["id"]
    resp = client.delete(
        f"/sessoes/{sessao_id}/materiais/{material_id}", headers=cabecalhos
    )
    assert resp.status_code == 204
    indice = client.get(f"/sessoes/{sessao_id}/materiais/indice", headers=cabecalhos)
    assert indice.json()["materiais"] == []


def test_confirmar_indice_congela_a_sessao(client):
    cabecalhos = _auth(client)
    sessao_id = _sessao(client, cabecalhos)
    _enviar(client, cabecalhos, sessao_id)

    confirmacao = client.post(
        f"/sessoes/{sessao_id}/materiais/confirmar", headers=cabecalhos
    )
    assert confirmacao.status_code == 200
    assert confirmacao.json()["confirmado"] is True

    tardio = _enviar(
        client,
        cabecalhos,
        sessao_id,
        dados=txt_bytes("outro material com conteúdo suficiente aqui"),
        nome="extra.txt",
        tipo="livro",
    )
    assert tardio.status_code == 409
    assert tardio.json()["codigo"] == "SESSAO_ESTADO_INVALIDO"


def test_confirmar_indice_vazio_retorna_409(client):
    cabecalhos = _auth(client)
    sessao_id = _sessao(client, cabecalhos)
    resp = client.post(f"/sessoes/{sessao_id}/materiais/confirmar", headers=cabecalhos)
    assert resp.status_code == 409
    assert resp.json()["codigo"] == "INDICE_VAZIO"


def test_schemas_de_material_aparecem_no_swagger(client):
    schema = client.get("/openapi.json").json()
    assert "/sessoes/{sessao_id}/materiais" in schema["paths"]
    componentes = schema["components"]["schemas"]
    assert "MaterialResposta" in componentes
    assert "IndiceResposta" in componentes
    for proibido in ("chave_armazenamento", "hash_sha256"):
        assert proibido not in componentes["MaterialResposta"]["properties"]


def test_confirmar_indexa_os_materiais_antes_de_congelar(client, db_session):
    from backend.app.models.materiais import ChunkMaterial, MaterialReferencia

    cabecalhos = _auth(client)
    sessao_id = _sessao(client, cabecalhos)
    _enviar(client, cabecalhos, sessao_id)

    assert db_session.query(ChunkMaterial).count() == 0

    resposta = client.post(
        f"/sessoes/{sessao_id}/materiais/confirmar", headers=cabecalhos
    )
    assert resposta.status_code == 200
    assert resposta.json()["confirmado"] is True

    assert db_session.query(ChunkMaterial).count() > 0
    material = db_session.query(MaterialReferencia).one()
    assert material.indexado_em is not None
    assert material.n_chunks > 0
