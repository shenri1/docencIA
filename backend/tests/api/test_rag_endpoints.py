from backend.app.exceptions import FalhaRerankException
from backend.app.main import app
from backend.app.services.rag.rerank import get_reranker
from backend.tests.fabricas import pdf_com_texto

PDF = pdf_com_texto(["Busca em largura percorre o grafo por níveis, camada a camada."])
SESSAO = {
    "disciplina": "Algoritmos",
    "periodo": "2026.2",
    "k_alternativas": 5,
    "p_f": 30,
    "p_m": 40,
    "p_d": 30,
}


def _auth(client, credencial="rag001") -> dict[str, str]:
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


def _sessao_confirmada(client, cabecalhos) -> int:
    sessao_id = _sessao(client, cabecalhos)
    client.post(
        f"/sessoes/{sessao_id}/materiais",
        headers=cabecalhos,
        files={"arquivo": ("aula.pdf", PDF, "application/pdf")},
        data={"tipo": "pdf"},
    )
    client.post(f"/sessoes/{sessao_id}/materiais/confirmar", headers=cabecalhos)
    return sessao_id


def test_busca_sem_token_e_401(client):
    assert client.get("/sessoes/1/buscar", params={"q": "grafos"}).status_code == 401


def test_busca_com_q_curto_demais_e_422(client):
    cabecalhos = _auth(client)
    resposta = client.get("/sessoes/1/buscar", params={"q": "ab"}, headers=cabecalhos)
    assert resposta.status_code == 422


def test_busca_em_sessao_inexistente_e_404(client):
    cabecalhos = _auth(client)
    resposta = client.get(
        "/sessoes/999999/buscar", params={"q": "grafos"}, headers=cabecalhos
    )
    assert resposta.status_code == 404


def test_busca_em_sessao_de_outro_docente_e_404(client):
    dono = _auth(client, "rag-dono")
    sessao_id = _sessao_confirmada(client, dono)
    intruso = _auth(client, "rag-intruso")
    resposta = client.get(
        f"/sessoes/{sessao_id}/buscar", params={"q": "grafos"}, headers=intruso
    )
    assert resposta.status_code == 404


def test_busca_em_sessao_nao_confirmada_e_409(client):
    cabecalhos = _auth(client)
    sessao_id = _sessao(client, cabecalhos)
    resposta = client.get(
        f"/sessoes/{sessao_id}/buscar", params={"q": "grafos"}, headers=cabecalhos
    )
    assert resposta.status_code == 409
    assert resposta.json()["codigo"] == "INDICE_NAO_CONFIRMADO"


def test_busca_devolve_trechos_com_fonte_rastreavel(client):
    cabecalhos = _auth(client)
    sessao_id = _sessao_confirmada(client, cabecalhos)
    resposta = client.get(
        f"/sessoes/{sessao_id}/buscar",
        params={"q": "busca em largura"},
        headers=cabecalhos,
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo
    assert corpo[0]["identificador_curto"] == "P1"
    assert corpo[0]["localizacao"]
    assert "chave_armazenamento" not in corpo[0]


def test_reranker_fora_responde_502_e_nao_degrada_em_silencio(client):
    """Ordem vetorial pura seria pior sem ninguém perceber: falha alta."""
    cabecalhos = _auth(client)
    sessao_id = _sessao_confirmada(client, cabecalhos)

    class RerankerFora:
        def reordenar(self, consulta, documentos, top_n):
            raise FalhaRerankException("connection refused")

    app.dependency_overrides[get_reranker] = RerankerFora
    try:
        resposta = client.get(
            f"/sessoes/{sessao_id}/buscar",
            params={"q": "busca em largura"},
            headers=cabecalhos,
        )
    finally:
        app.dependency_overrides.pop(get_reranker, None)
    assert resposta.status_code == 502
    assert resposta.json()["codigo"] == "FALHA_RERANK"


def test_rota_de_busca_esta_documentada_no_swagger(client):
    schema = client.get("/openapi.json").json()
    assert "/sessoes/{sessao_id}/buscar" in schema["paths"]
    assert "TrechoResposta" in schema["components"]["schemas"]
