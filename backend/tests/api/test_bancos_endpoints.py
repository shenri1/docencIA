from backend.app.api.deps import get_provedor
from backend.app.main import app
from backend.app.models.identidade import SessaoGeracao
from backend.app.services.geracao.banco_service import gerar_banco
from backend.tests.conftest import _auth
from backend.tests.fabrica_banco import criar_banco, criar_questao_objetiva
from backend.tests.services.geracao.duplos import ProvedorLLMFake
from backend.tests.services.geracao.test_banco_service import (
    preparar,
    roteiro,
    roteiro_variacao,
)

SESSAO = {
    "disciplina": "Algoritmos",
    "periodo": "2026.2",
    "tema_escopo": "Grafos",
    "area_do_conhecimento": "Computação",
    "k_alternativas": 5,
    "p_f": 30,
    "p_m": 40,
    "p_d": 30,
}


def preparar_banco(db_session, client, credencial="prof-bancos"):
    """Cria docente pelo endpoint (para ter token) e um banco dele."""
    headers = _auth(client, credencial)
    sessao_id = client.post("/sessoes", headers=headers, json=SESSAO).json()["id"]
    sessao = db_session.get(SessaoGeracao, sessao_id)
    banco = criar_banco(db_session, sessao, n_objetivas=3)
    for numero in (1, 2, 3):
        criar_questao_objetiva(db_session, banco, numero=numero)
    db_session.commit()
    return headers, banco


def test_get_banco_sem_token_responde_401(client, db_session):
    _, banco = preparar_banco(db_session, client)
    assert client.get(f"/bancos/{banco.id}").status_code == 401


def test_get_banco_de_outro_docente_responde_404(client, db_session):
    _, banco = preparar_banco(db_session, client, "prof-dono")
    outro = _auth(client, "prof-intruso")
    assert client.get(f"/bancos/{banco.id}", headers=outro).status_code == 404


def test_get_banco_devolve_cabecalho_e_questoes(client, db_session):
    headers, banco = preparar_banco(db_session, client)
    corpo = client.get(f"/bancos/{banco.id}", headers=headers).json()
    assert corpo["rotulo"] == "v1.r0"
    assert [q["numero"] for q in corpo["questoes"]] == [1, 2, 3]
    assert corpo["questoes"][0]["letra_correta"] is None


def test_get_banco_com_gabarito_revela_a_correta(client, db_session):
    headers, banco = preparar_banco(db_session, client)
    corpo = client.get(
        f"/bancos/{banco.id}", headers=headers, params={"com_gabarito": True}
    ).json()
    assert corpo["questoes"][0]["letra_correta"] == "A"


def test_get_banco_com_ate_menor_que_de_responde_422(client, db_session):
    headers, banco = preparar_banco(db_session, client)
    resposta = client.get(
        f"/bancos/{banco.id}", headers=headers, params={"de": 5, "ate": 2}
    )
    assert resposta.status_code == 422


def test_post_exclusoes_devolve_relatorio(client, db_session):
    headers, banco = preparar_banco(db_session, client)
    resposta = client.post(
        f"/bancos/{banco.id}/exclusoes",
        headers=headers,
        json={"numeros": [2], "revisao_esperada": 0},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["revisao"] == 1
    assert corpo["evento"] == "exclusao"
    assert corpo["n_final"] == 2


def test_post_exclusoes_com_revisao_errada_responde_409(client, db_session):
    headers, banco = preparar_banco(db_session, client)
    resposta = client.post(
        f"/bancos/{banco.id}/exclusoes",
        headers=headers,
        json={"numeros": [2], "revisao_esperada": 9},
    )
    assert resposta.status_code == 409
    assert resposta.json()["codigo"] == "REVISAO_DESATUALIZADA"


def test_post_exclusoes_com_lista_vazia_responde_422(client, db_session):
    headers, banco = preparar_banco(db_session, client)
    resposta = client.post(
        f"/bancos/{banco.id}/exclusoes",
        headers=headers,
        json={"numeros": [], "revisao_esperada": 0},
    )
    assert resposta.status_code == 422


def test_post_congelar_devolve_relatorio_de_congelamento(client, db_session):
    headers, banco = preparar_banco(db_session, client)
    resposta = client.post(
        f"/bancos/{banco.id}/congelar", headers=headers, json={"revisao_esperada": 0}
    )
    assert resposta.status_code == 200
    assert resposta.json()["evento"] == "congelamento"


def test_get_relatorios_lista_em_ordem(client, db_session):
    headers, banco = preparar_banco(db_session, client)
    client.post(
        f"/bancos/{banco.id}/exclusoes",
        headers=headers,
        json={"numeros": [1], "revisao_esperada": 0},
    )
    client.post(
        f"/bancos/{banco.id}/congelar", headers=headers, json={"revisao_esperada": 1}
    )
    corpo = client.get(f"/bancos/{banco.id}/relatorios", headers=headers).json()
    assert [r["revisao"] for r in corpo] == [1, 2]


def test_post_rejeitar_sem_candidata_responde_409(client, db_session):
    headers, banco = preparar_banco(db_session, client)
    resposta = client.post(
        f"/bancos/{banco.id}/questoes/1/substituicao/rejeitar", headers=headers
    )
    assert resposta.status_code == 409
    assert resposta.json()["codigo"] == "SEM_CANDIDATA_PENDENTE"


def test_nenhuma_rota_de_banco_apaga_dado_de_composicao():
    """Invariante da seção H: nada do histórico de composição é apagado. Usa
    app.openapi(), não app.routes — app.routes guarda `_IncludedRouter` nesta
    versão do FastAPI e é preguiçoso."""
    caminhos = app.openapi()["paths"]
    de_banco = {
        caminho: list(metodos)
        for caminho, metodos in caminhos.items()
        if caminho.startswith("/bancos")
    }
    assert de_banco, "nenhuma rota /bancos registrada"
    assert all("delete" not in metodos for metodos in de_banco.values())


def test_schema_do_banco_nao_expoe_justificativa_nem_rascunho():
    schemas = app.openapi()["components"]["schemas"]
    questao = schemas["QuestaoResposta"]["properties"]
    assert "justificativa" not in questao
    assert "rascunho" not in questao


def test_propor_e_aceitar_pela_api(
    client, db_session, armazenamento, embeddings_fake, reranker_fake
):
    headers = _auth(client, "prof-subst")
    sessao_id = client.post("/sessoes", headers=headers, json=SESSAO).json()["id"]
    sessao = db_session.get(SessaoGeracao, sessao_id)
    preparar(db_session, armazenamento, sessao)
    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake(roteiro(2)),
        sessao,
        n_objetivas=2,
        n_discursivas=0,
        versao="v1",
    )

    app.dependency_overrides[get_provedor] = lambda: ProvedorLLMFake(roteiro_variacao(1))
    try:
        proposta = client.post(
            f"/bancos/{resumo.banco_id}/questoes/1/substituicao", headers=headers
        )
    finally:
        app.dependency_overrides.pop(get_provedor, None)
    assert proposta.status_code == 201
    assert proposta.json()["candidata"]["letra_correta"] == "A"

    aceite = client.post(
        f"/bancos/{resumo.banco_id}/questoes/1/substituicao/aceitar",
        headers=headers,
        json={"revisao_esperada": resumo.revisao},
    )
    assert aceite.status_code == 200
    assert aceite.json()["evento"] == "substituicao"
