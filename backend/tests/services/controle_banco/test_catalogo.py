from backend.app.domain import EstadoQuestao, FaixaDificuldade, TipoQuestao
from backend.app.services.controle_banco.catalogo import ItemCatalogo, catalogar
from backend.tests.api.test_provas_endpoints import preparar
from backend.tests.conftest import _auth
from backend.tests.fabrica_banco import (
    criar_banco,
    criar_questao_discursiva,
    criar_questao_objetiva,
)


def test_catalogo_lista_ativas_por_numero(db_session, sessao_rascunho):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=2, n_discursivas=1)
    criar_questao_objetiva(db_session, banco, numero=2, faixa=FaixaDificuldade.DIFICIL)
    criar_questao_objetiva(db_session, banco, numero=1, estado=EstadoQuestao.EXCLUIDA)
    criar_questao_discursiva(db_session, banco, numero=3)
    db_session.commit()

    assert catalogar(db_session, banco) == [
        ItemCatalogo(2, TipoQuestao.OBJETIVA, "Grafos", FaixaDificuldade.DIFICIL),
        ItemCatalogo(3, TipoQuestao.DISCURSIVA, "Grafos", FaixaDificuldade.MEDIA),
    ]


def test_catalogo_preserva_tema_ausente(db_session, sessao_rascunho):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=1)
    questao = criar_questao_objetiva(db_session, banco, numero=1)
    questao.tema = None
    db_session.commit()

    assert catalogar(db_session, banco)[0].tema is None


def test_get_catalogo(client, db_session):
    headers, banco = preparar(client, db_session, "prof-catalogo")
    resposta = client.get(f"/bancos/{banco.id}/catalogo", headers=headers)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [i["numero"] for i in corpo] == list(range(1, 26))
    assert corpo[0] == {
        "numero": 1,
        "tipo": "objetiva",
        "tema": "Grafos",
        "faixa": "facil",
    }


def test_get_catalogo_sem_token_e_401(client, db_session):
    _, banco = preparar(client, db_session, "prof-catalogo-401")
    assert client.get(f"/bancos/{banco.id}/catalogo").status_code == 401


def test_get_catalogo_de_banco_alheio_e_404(client, db_session):
    _, banco = preparar(client, db_session, "prof-catalogo-dono")
    outro = _auth(client, "prof-catalogo-intruso")
    assert client.get(f"/bancos/{banco.id}/catalogo", headers=outro).status_code == 404
