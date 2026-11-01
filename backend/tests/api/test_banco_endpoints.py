import pytest

from backend.app.api.deps import get_provedor
from backend.app.main import app
from backend.app.models.identidade import SessaoGeracao
from backend.tests.conftest import _auth
from backend.tests.services.geracao.duplos import ProvedorLLMFake
from backend.tests.services.geracao.test_banco_service import preparar, roteiro


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


@pytest.mark.parametrize(
    ("credencial", "extra", "status"),
    [
        ("lote-ok", {"limite": 1, "apos": 3}, 404),
        ("lote-zero", {"limite": 0}, 422),
        ("lote-26", {"limite": 26}, 422),
        ("lote-neg", {"apos": -1}, 422),
    ],
)
def test_limite_e_apos_validados_no_schema(client, credencial, extra, status):
    """404 = passou da validação e esbarrou na sessão inexistente."""
    cabecalhos = _auth(client, credencial)
    resposta = client.post(
        "/sessoes/999999/banco",
        json={"n_objetivas": 5, "n_discursivas": 0, "versao": "v1", **extra},
        headers=cabecalhos,
    )
    assert resposta.status_code == status


def test_resumo_expoe_onde_o_lote_parou(client):
    componentes = client.get("/openapi.json").json()["components"]["schemas"]
    propriedades = componentes["ResumoBancoResposta"]["properties"]
    assert {"ultimo_numero", "restantes"} <= set(propriedades)


def test_gerar_banco_pela_api_chama_o_juiz(
    client, db_session, armazenamento, juiz_fake
):
    headers = _auth(client, "prof-juiz")
    sessao_id = client.post(
        "/sessoes",
        headers=headers,
        json={
            "disciplina": "Algoritmos",
            "periodo": "2026.2",
            "tema_escopo": "Grafos",
            "area_do_conhecimento": "Computação",
            "k_alternativas": 5,
            "p_f": 30,
            "p_m": 40,
            "p_d": 30,
        },
    ).json()["id"]
    preparar(db_session, armazenamento, db_session.get(SessaoGeracao, sessao_id))
    app.dependency_overrides[get_provedor] = lambda: ProvedorLLMFake(roteiro(2))
    try:
        resposta = client.post(
            f"/sessoes/{sessao_id}/banco",
            headers=headers,
            json={"n_objetivas": 2, "n_discursivas": 0, "versao": "v1"},
        )
    finally:
        app.dependency_overrides.pop(get_provedor, None)
    assert resposta.status_code == 201, resposta.json()
    assert resposta.json()["geradas"] == 2
    assert len(juiz_fake.chamadas) == 2
