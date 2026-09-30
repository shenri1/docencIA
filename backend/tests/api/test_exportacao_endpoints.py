from backend.tests.api.test_provas_endpoints import montar, preparar
from backend.tests.conftest import _auth

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def exportado(client, db_session, credencial):
    headers, banco = preparar(client, db_session, credencial)
    montar(client, headers, banco)
    resposta = client.post(f"/bancos/{banco.id}/exportacoes", headers=headers)
    return headers, banco, resposta


def test_post_exportacoes_sem_token_responde_401(client, db_session):
    _, banco = preparar(client, db_session, "prof-exp-401")
    assert client.post(f"/bancos/{banco.id}/exportacoes").status_code == 401


def test_post_exportacoes_devolve_os_dois_registros(client, db_session):
    _, _, resposta = exportado(client, db_session, "prof-exp-ok")
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert sorted(r["tipo"] for r in corpo) == ["conteudo_puro", "metadados"]
    assert all(len(r["hash_conteudo"]) == 64 for r in corpo)
    # A chave de armazenamento nunca sai.
    assert all("caminho_arquivo" not in r for r in corpo)


def test_estado_incoerente_responde_409_com_o_codigo(client, db_session):
    headers, banco = preparar(client, db_session, "prof-exp-409")
    # Sem provas montadas.
    resposta = client.post(f"/bancos/{banco.id}/exportacoes", headers=headers)
    assert resposta.status_code == 409
    assert resposta.json()["codigo"] == "INCONSISTENCIA_DE_ESTADO"


def test_get_exportacoes_lista_o_historico(client, db_session):
    headers, banco, _ = exportado(client, db_session, "prof-exp-lista")
    corpo = client.get(f"/bancos/{banco.id}/exportacoes", headers=headers).json()
    assert len(corpo) == 2


def test_download_entrega_o_docx_com_cabecalhos(client, db_session):
    import hashlib

    headers, _, resposta = exportado(client, db_session, "prof-exp-baixa")
    registro = resposta.json()[0]
    arquivo = client.get(f"/exportacoes/{registro['id']}/arquivo", headers=headers)
    assert arquivo.status_code == 200
    assert arquivo.headers["content-type"] == DOCX
    assert "attachment" in arquivo.headers["content-disposition"]
    assert ".docx" in arquivo.headers["content-disposition"]
    assert hashlib.sha256(arquivo.content).hexdigest() == registro["hash_conteudo"]


def test_download_de_exportacao_alheia_responde_404(client, db_session):
    _, _, resposta = exportado(client, db_session, "prof-exp-dono")
    outro = _auth(client, "prof-exp-intruso")
    registro = resposta.json()[0]
    assert (
        client.get(f"/exportacoes/{registro['id']}/arquivo", headers=outro).status_code
        == 404
    )
