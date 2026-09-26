from backend.app.domain import PerfilDocente
from backend.app.models.identidade import Docente

CORPO = {
    "versao": "1.0.0",
    "papel_definido": "docente universitário elaborador de questões",
    "disciplina": "Algoritmos",
    "periodo": "2026.2",
    "area_do_conhecimento": "Computação",
    "tema_escopo": "Grafos",
    "k_alternativas": 5,
    "n_faceis": 5,
    "n_medias": 30,
    "n_dificeis": 15,
}


def _auth(client, credencial="prompt001") -> dict[str, str]:
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


def _promover(db_session, credencial: str) -> None:
    """O self-signup cria sempre perfil `docente`; estas rotas
    exigem `administrador`."""
    docente = (
        db_session.query(Docente).filter_by(credencial_institucional=credencial).one()
    )
    docente.perfil = PerfilDocente.ADMINISTRADOR
    db_session.commit()


def test_listar_sem_token_e_401(client):
    assert client.get("/prompts").status_code == 401


def test_docente_comum_nao_acessa_e_403(client):
    cabecalhos = _auth(client)
    assert client.get("/prompts", headers=cabecalhos).status_code == 403


def test_administrador_registra_versao_201(client, db_session):
    cabecalhos = _auth(client, "admin001")
    _promover(db_session, "admin001")

    resposta = client.post("/prompts", json=CORPO, headers=cabecalhos)
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["versao"] == "1.0.0"
    assert corpo["ativo"] is False
    assert "Algoritmos" in corpo["conteudo"]
    assert "{{" not in corpo["conteudo"]


def test_versao_duplicada_e_409(client, db_session):
    cabecalhos = _auth(client, "admin002")
    _promover(db_session, "admin002")
    client.post("/prompts", json=CORPO, headers=cabecalhos)

    resposta = client.post("/prompts", json=CORPO, headers=cabecalhos)
    assert resposta.status_code == 409
    assert resposta.json()["codigo"] == "VERSAO_PROMPT_DUPLICADA"


def test_ativo_sem_nenhuma_versao_ativa_e_409(client, db_session):
    cabecalhos = _auth(client, "admin003")
    _promover(db_session, "admin003")
    client.post("/prompts", json=CORPO, headers=cabecalhos)

    resposta = client.get("/prompts/ativo", headers=cabecalhos)
    assert resposta.status_code == 409
    assert resposta.json()["codigo"] == "NENHUM_PROMPT_ATIVO"


def test_ativar_e_rollback(client, db_session):
    cabecalhos = _auth(client, "admin004")
    _promover(db_session, "admin004")
    client.post("/prompts", json=CORPO, headers=cabecalhos)
    client.post("/prompts", json={**CORPO, "versao": "2.0.0"}, headers=cabecalhos)

    client.post("/prompts/2.0.0/ativar", headers=cabecalhos)
    assert client.get("/prompts/ativo", headers=cabecalhos).json()["versao"] == "2.0.0"

    # Rollback: volta para a anterior.
    resposta = client.post("/prompts/1.0.0/ativar", headers=cabecalhos)
    assert resposta.status_code == 200
    assert client.get("/prompts/ativo", headers=cabecalhos).json()["versao"] == "1.0.0"


def test_ativar_versao_inexistente_e_404(client, db_session):
    cabecalhos = _auth(client, "admin005")
    _promover(db_session, "admin005")
    assert client.post("/prompts/9.9.9/ativar", headers=cabecalhos).status_code == 404


def test_historico_vem_do_mais_novo_para_o_mais_antigo(client, db_session):
    cabecalhos = _auth(client, "admin006")
    _promover(db_session, "admin006")
    client.post("/prompts", json=CORPO, headers=cabecalhos)
    client.post("/prompts", json={**CORPO, "versao": "2.0.0"}, headers=cabecalhos)

    versoes = [p["versao"] for p in client.get("/prompts", headers=cabecalhos).json()]
    assert versoes == ["2.0.0", "1.0.0"]

