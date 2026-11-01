import pytest

from backend.app.main import app
from backend.app.models.provas import Prova
from backend.tests.conftest import _auth


def preparar(client, db_session, credencial="prof-provas"):
    """Sessão, banco congelado de 25 objetivas, pelo caminho direto."""
    from backend.app.domain import FaixaDificuldade
    from backend.app.models.identidade import SessaoGeracao
    from backend.app.services.controle_banco.exclusao_service import congelar_banco
    from backend.tests.fabrica_banco import criar_banco, criar_questao_objetiva

    headers = _auth(client, credencial)
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
    sessao = db_session.get(SessaoGeracao, sessao_id)
    banco = criar_banco(db_session, sessao, n_objetivas=25)
    numero = 0
    for faixa, quantas in (
        (FaixaDificuldade.FACIL, 7),
        (FaixaDificuldade.MEDIA, 10),
        (FaixaDificuldade.DIFICIL, 8),
    ):
        for _ in range(quantas):
            numero += 1
            criar_questao_objetiva(
                db_session, banco, numero=numero, faixa=faixa, subtema=f"s{numero}"
            )
    db_session.commit()
    # Pelo serviço do controle do banco: congelado sem relatório de congelamento é
    # incoerente, e a montagem recusa.
    congelar_banco(db_session, sessao.docente, banco, banco.revisao)
    return headers, banco


def montar(client, headers, banco, n_objetivas=10, n_discursivas=0):
    return client.post(
        f"/bancos/{banco.id}/provas",
        headers=headers,
        json={
            "n_objetivas": n_objetivas,
            "n_discursivas": n_discursivas,
            "revisao_esperada": banco.revisao,
        },
    )


def test_post_provas_sem_token_responde_401(client, db_session):
    _, banco = preparar(client, db_session)
    assert client.post(f"/bancos/{banco.id}/provas", json={}).status_code == 401


def test_post_provas_de_banco_alheio_responde_404(client, db_session):
    _, banco = preparar(client, db_session, "prof-dono-provas")
    outro = _auth(client, "prof-intruso-provas")
    resposta = client.post(
        f"/bancos/{banco.id}/provas",
        headers=outro,
        json={"n_objetivas": 10, "n_discursivas": 0, "revisao_esperada": 0},
    )
    assert resposta.status_code == 404


def test_post_provas_monta_e_verifica(client, db_session):
    headers, banco = preparar(client, db_session)
    resposta = montar(client, headers, banco)
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["verificacao"]["violacoes"] == []
    assert corpo["revisao_banco"] == banco.revisao
    assert corpo["prova_a_id"] != corpo["prova_b_id"]


def test_post_provas_com_soma_zero_responde_422(client, db_session):
    headers, banco = preparar(client, db_session)
    resposta = client.post(
        f"/bancos/{banco.id}/provas",
        headers=headers,
        json={"n_objetivas": 0, "n_discursivas": 0, "revisao_esperada": 0},
    )
    assert resposta.status_code == 422


def test_get_prova_traz_alternativas_na_ordem_da_prova(client, db_session):
    headers, banco = preparar(client, db_session)
    prova_a_id = montar(client, headers, banco).json()["prova_a_id"]
    corpo = client.get(f"/provas/{prova_a_id}", headers=headers).json()

    assert corpo["versao"] == "A"
    assert len(corpo["itens"]) == 10
    assert [i["posicao"] for i in corpo["itens"]] == list(range(1, 11))
    letras = [a["letra"] for a in corpo["itens"][0]["alternativas"]]
    assert letras == ["A", "B", "C", "D", "E"]


def test_get_prova_de_outro_docente_responde_404(client, db_session):
    headers, banco = preparar(client, db_session, "prof-dono-get")
    prova_a_id = montar(client, headers, banco).json()["prova_a_id"]
    outro = _auth(client, "prof-intruso-get")
    assert client.get(f"/provas/{prova_a_id}", headers=outro).status_code == 404


def test_get_prova_marca_desatualizada_depois_de_substituicao(client, db_session):
    headers, banco = preparar(client, db_session)
    prova_a_id = montar(client, headers, banco).json()["prova_a_id"]
    assert (
        client.get(f"/provas/{prova_a_id}", headers=headers).json()["desatualizada"]
        is False
    )

    # Substituição aceita move banco.revisao — é o que o controle do banco prometeu que
    # tornaria "inconsistência de estado" uma comparação de inteiros.
    banco.revisao += 1
    db_session.commit()
    corpo = client.get(f"/provas/{prova_a_id}", headers=headers).json()
    assert corpo["desatualizada"] is True
    assert corpo["banco_revisao_atual"] == banco.revisao


def test_get_verificacao(client, db_session):
    headers, banco = preparar(client, db_session)
    prova_a_id = montar(client, headers, banco).json()["prova_a_id"]
    corpo = client.get(f"/provas/{prova_a_id}/verificacao", headers=headers).json()
    assert corpo["violacoes"] == []
    assert corpo["posicoes_objetivas"] == 10


def test_schema_da_prova_nao_revela_a_correta():
    """Prova é o que o aluno vê. Gabarito é outro endpoint."""
    schemas = app.openapi()["components"]["schemas"]
    item = schemas["ItemProvaResposta"]["properties"]
    alternativa = schemas["AlternativaProvaResposta"]["properties"]
    proibidos = {
        "letra_atribuida",
        "ordem_alternativas",
        "aspectos_esperados",
        "justificativa",
        "fontes",
        "fontes_internas",
    }
    assert proibidos.isdisjoint(item)
    assert "correta" not in alternativa
    assert set(alternativa) == {"letra", "texto"}


def test_gabarito_sem_token_responde_401(client, db_session):
    headers, banco = preparar(client, db_session, "prof-gab-401")
    prova_a_id = montar(client, headers, banco).json()["prova_a_id"]
    resposta = client.get(f"/provas/{prova_a_id}/gabarito?modalidade=simples")
    assert resposta.status_code == 401


def test_gabarito_de_prova_alheia_responde_404(client, db_session):
    headers, banco = preparar(client, db_session, "prof-gab-dono")
    prova_a_id = montar(client, headers, banco).json()["prova_a_id"]
    outro = _auth(client, "prof-gab-intruso")
    resposta = client.get(
        f"/provas/{prova_a_id}/gabarito?modalidade=simples", headers=outro
    )
    assert resposta.status_code == 404


def test_gabarito_sem_modalidade_responde_422(client, db_session):
    """Sem default de propósito: o comentado expõe a justificativa estruturada,
    e isso não deve acontecer por omissão de parâmetro."""
    headers, banco = preparar(client, db_session, "prof-gab-422")
    prova_a_id = montar(client, headers, banco).json()["prova_a_id"]
    resposta = client.get(f"/provas/{prova_a_id}/gabarito", headers=headers)
    assert resposta.status_code == 422


def test_gabarito_simples(client, db_session):
    headers, banco = preparar(client, db_session, "prof-gab-simples")
    prova_a_id = montar(client, headers, banco).json()["prova_a_id"]
    corpo = client.get(
        f"/provas/{prova_a_id}/gabarito?modalidade=simples", headers=headers
    ).json()
    assert corpo["modalidade"] == "simples"
    assert corpo["completo"] is True
    assert len(corpo["itens"]) == 10
    assert corpo["itens"][0]["letra"] in "ABCDE"
    assert corpo["itens"][0]["justificativa_correta"] is None


def test_gabarito_comentado(client, db_session):
    headers, banco = preparar(client, db_session, "prof-gab-comentado")
    prova_a_id = montar(client, headers, banco).json()["prova_a_id"]
    corpo = client.get(
        f"/provas/{prova_a_id}/gabarito?modalidade=comentado", headers=headers
    ).json()
    item = corpo["itens"][0]
    assert item["justificativa_correta"]
    assert len(item["invalidacoes"]) == 4
    assert item["fontes"][0]["trecho_base"]


@pytest.mark.parametrize("n_objetivas", [10, 15])
def test_get_provas_devolve_o_que_o_post_devolveu(client, db_session, n_objetivas):
    """15 por prova num banco de 25 força questões compartilhadas: a leitura tem
    de recalcular as mesmas que a montagem escolheu."""
    headers, banco = preparar(client, db_session, f"prof-get-provas-{n_objetivas}")
    montada = montar(client, headers, banco, n_objetivas=n_objetivas)
    assert montada.status_code == 201

    lida = client.get(f"/bancos/{banco.id}/provas", headers=headers)

    assert lida.status_code == 200
    assert lida.json() == montada.json()


def test_get_provas_recalcula_sem_subtema_do_estado_gravado(client, db_session):
    headers, banco = preparar(client, db_session, "prof-get-sem-subtema")
    montada = montar(client, headers, banco).json()
    prova_a = db_session.get(Prova, montada["prova_a_id"])
    prova_a.itens[0].questao.subtema = None
    db_session.commit()

    corpo = client.get(f"/bancos/{banco.id}/provas", headers=headers).json()

    assert corpo["sem_subtema"] == 1


def test_get_provas_sem_provas_responde_404(client, db_session):
    headers, banco = preparar(client, db_session, "prof-get-sem-provas")

    resposta = client.get(f"/bancos/{banco.id}/provas", headers=headers)

    assert resposta.status_code == 404
    assert resposta.json()["codigo"] == "PROVAS_NAO_MONTADAS"


def test_get_provas_de_banco_alheio_responde_404(client, db_session):
    headers, banco = preparar(client, db_session, "prof-dono-get-provas")
    assert montar(client, headers, banco).status_code == 201
    outro = _auth(client, "prof-intruso-get-provas")

    resposta = client.get(f"/bancos/{banco.id}/provas", headers=outro)

    assert resposta.status_code == 404
    assert resposta.json()["codigo"] == "BANCO_NAO_ENCONTRADO"
