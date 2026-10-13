import pytest

from backend.app.api.deps import get_provedor
from backend.app.main import app
from backend.app.models.identidade import SessaoGeracao
from backend.app.services.geracao.banco_service import gerar_banco
from backend.tests.conftest import _auth
from backend.tests.services.geracao.duplos import ProvedorLLMFake
from backend.tests.services.geracao.test_banco_service import (
    preparar,
    roteiro,
    roteiro_variacao,
)

SESSAO = {
    "disciplina": "Algoritmos",
    "periodo": "2026.2",
    "k_alternativas": 5,
    "p_f": 30,
    "p_m": 40,
    "p_d": 30,
}


def _sessao(client, headers, **extra) -> int:
    resposta = client.post("/sessoes", headers=headers, json={**SESSAO, **extra})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def test_criar_sessao_com_orientacoes_grava_ativas(client):
    headers = _auth(client, "prof-ori1")
    sessao_id = _sessao(client, headers, orientacoes=["  prefiro exemplos práticos  "])

    lista = client.get(f"/sessoes/{sessao_id}/orientacoes", headers=headers).json()

    assert [(o["origem"], o["estado"], o["o_que_mudar"]) for o in lista] == [
        ("sessao", "ativa", "prefiro exemplos práticos")
    ]
    assert lista[0]["cruzar_com"] is None


@pytest.mark.parametrize(
    "orientacoes",
    [["x"] * 6, ["a" * 501], ["   "]],
    ids=["seis", "longa", "so-espacos"],
)
def test_criar_sessao_com_orientacoes_invalidas_responde_422(client, orientacoes):
    headers = _auth(client, "prof-ori2")
    resposta = client.post(
        "/sessoes", headers=headers, json={**SESSAO, "orientacoes": orientacoes}
    )
    assert resposta.status_code == 422


def test_acrescentar_e_desativar_pela_api(client):
    headers = _auth(client, "prof-ori3")
    sessao_id = _sessao(client, headers)

    criada = client.post(
        f"/sessoes/{sessao_id}/orientacoes",
        headers=headers,
        json={"o_que_mudar": "enunciados curtos"},
    )
    assert criada.status_code == 201
    oid = criada.json()["id"]

    for _ in range(2):  # idempotente
        desativada = client.post(
            f"/sessoes/{sessao_id}/orientacoes/{oid}/desativar", headers=headers
        )
        assert desativada.status_code == 200
        assert desativada.json()["estado"] == "inativa"


def test_sexta_orientacao_responde_409(client):
    headers = _auth(client, "prof-ori4")
    sessao_id = _sessao(client, headers, orientacoes=[f"o{i}" for i in range(5)])

    resposta = client.post(
        f"/sessoes/{sessao_id}/orientacoes", headers=headers, json={"o_que_mudar": "mais"}
    )

    assert resposta.status_code == 409
    assert resposta.json()["codigo"] == "LIMITE_ORIENTACOES"
    assert resposta.json()["ativas"] == 5


def test_rotas_de_orientacao_de_outro_docente_respondem_404(client):
    dono = _auth(client, "prof-ori5")
    sessao_id = _sessao(client, dono, orientacoes=["a"])
    oid = client.get(f"/sessoes/{sessao_id}/orientacoes", headers=dono).json()[0]["id"]
    intruso = _auth(client, "prof-ori6")

    assert client.get(f"/sessoes/{sessao_id}/orientacoes", headers=intruso).status_code == 404
    assert (
        client.post(
            f"/sessoes/{sessao_id}/orientacoes", headers=intruso, json={"o_que_mudar": "x"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/sessoes/{sessao_id}/orientacoes/{oid}/desativar", headers=intruso
        ).status_code
        == 404
    )


def _banco_gerado(client, db_session, armazenamento, emb, rer, credencial):
    headers = _auth(client, credencial)
    sessao_id = _sessao(client, headers)
    sessao = db_session.get(SessaoGeracao, sessao_id)
    preparar(db_session, armazenamento, sessao)
    resumo = gerar_banco(
        db_session, emb, rer, ProvedorLLMFake(roteiro(2)), sessao,
        n_objetivas=2, n_discursivas=0, versao="v1",
    )
    return headers, sessao_id, resumo.banco_id


@pytest.mark.parametrize(
    "corpo", [{}, {"cruzar_com": "  ", "o_que_mudar": ""}, {"cruzar_com": "a" * 201}]
)
def test_direcao_invalida_responde_422(
    client, db_session, armazenamento, embeddings_fake, reranker_fake, corpo
):
    headers, _, banco_id = _banco_gerado(
        client, db_session, armazenamento, embeddings_fake, reranker_fake, "prof-ori7"
    )
    resposta = client.post(
        f"/bancos/{banco_id}/questoes/1/substituicao", headers=headers, json=corpo
    )
    assert resposta.status_code == 422


def test_variacao_guiada_pela_api_liga_a_candidata(
    client, db_session, armazenamento, embeddings_fake, reranker_fake
):
    headers, sessao_id, banco_id = _banco_gerado(
        client, db_session, armazenamento, embeddings_fake, reranker_fake, "prof-ori8"
    )
    app.dependency_overrides[get_provedor] = lambda: ProvedorLLMFake(roteiro_variacao(1))
    try:
        proposta = client.post(
            f"/bancos/{banco_id}/questoes/1/substituicao",
            headers=headers,
            json={"o_que_mudar": "use um exemplo de rede"},
        )
    finally:
        app.dependency_overrides.pop(get_provedor, None)

    assert proposta.status_code == 201
    [orientacao] = client.get(f"/sessoes/{sessao_id}/orientacoes", headers=headers).json()
    assert orientacao["estado"] == "pontual"
    assert proposta.json()["candidata"]["orientacoes_ids"] == [orientacao["id"]]

    desativar = client.post(
        f"/sessoes/{sessao_id}/orientacoes/{orientacao['id']}/desativar", headers=headers
    )
    assert desativar.status_code == 409
    assert desativar.json()["codigo"] == "ESTADO_ORIENTACAO_INVALIDO"

    banco = client.get(
        f"/bancos/{banco_id}", headers=headers, params={"incluir_historico": True}
    ).json()
    por_estado = {q["estado"]: q["orientacoes_ids"] for q in banco["questoes"]}
    assert por_estado["candidata"] == [orientacao["id"]]
    assert por_estado["ativa"] == []
