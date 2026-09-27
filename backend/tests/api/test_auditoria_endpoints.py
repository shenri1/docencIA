from backend.app.api.deps import get_provedor
from backend.app.main import app
from backend.app.models.identidade import SessaoGeracao
from backend.tests.conftest import _auth
from backend.tests.fabrica_banco import criar_banco, criar_questao_objetiva
from backend.tests.services.geracao.duplos import ProvedorLLMFake
from backend.tests.services.geracao.test_banco_service import preparar

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


def sem_achado() -> dict:
    return {"achados": []}


def preparar_banco(client, db_session, armazenamento, credencial="prof-auditoria", n=2):
    headers = _auth(client, credencial)
    sessao_id = client.post("/sessoes", headers=headers, json=SESSAO).json()["id"]
    sessao = db_session.get(SessaoGeracao, sessao_id)
    preparar(db_session, armazenamento, sessao)
    banco = criar_banco(db_session, sessao, n_objetivas=n)
    for numero in range(1, n + 1):
        criar_questao_objetiva(db_session, banco, numero=numero)
    db_session.commit()
    return headers, banco


def _auditar_com_fake(client, headers, banco_id, roteiro):
    app.dependency_overrides[get_provedor] = lambda: ProvedorLLMFake(roteiro)
    try:
        return client.post(f"/bancos/{banco_id}/auditoria", headers=headers)
    finally:
        app.dependency_overrides.pop(get_provedor, None)


def test_post_auditoria_sem_token_responde_401(client, db_session, armazenamento):
    _, banco = preparar_banco(client, db_session, armazenamento)
    assert client.post(f"/bancos/{banco.id}/auditoria").status_code == 401


def test_post_auditoria_de_banco_alheio_responde_404(client, db_session, armazenamento):
    _, banco = preparar_banco(client, db_session, armazenamento, "prof-dono-aud")
    outro = _auth(client, "prof-intruso-aud")
    assert client.post(f"/bancos/{banco.id}/auditoria", headers=outro).status_code == 404


def test_post_auditoria_devolve_resumo(client, db_session, armazenamento):
    headers, banco = preparar_banco(client, db_session, armazenamento)
    resposta = _auditar_com_fake(
        client, headers, banco.id, [sem_achado(), sem_achado()]
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["banco_id"] == banco.id
    assert corpo["auditadas"] == 2
    assert corpo["ja_auditadas"] == 0
    assert corpo["questoes"] == []
    assert corpo["proporcao_com_achado"] == "0.00"


def test_get_auditoria_antes_de_auditar_devolve_resumo_vazio(
    client, db_session, armazenamento
):
    headers, banco = preparar_banco(client, db_session, armazenamento)
    corpo = client.get(f"/bancos/{banco.id}/auditoria", headers=headers).json()
    assert corpo["auditadas"] == 0
    assert corpo["revisao_auditada"] == banco.revisao


def test_get_auditoria_depois_de_auditar_repete_os_contadores(
    client, db_session, armazenamento
):
    headers, banco = preparar_banco(client, db_session, armazenamento)
    _auditar_com_fake(client, headers, banco.id, [sem_achado(), sem_achado()])

    corpo = client.get(f"/bancos/{banco.id}/auditoria", headers=headers).json()
    assert corpo["auditadas"] == corpo["ja_auditadas"] == 2


def test_auditoria_nao_expoe_delete_nem_justificativa():
    """A invariante continua: nada de composição é apagado, e a
    justificativa estruturada nunca sai na resposta."""
    aberto = app.openapi()
    caminho = aberto["paths"]["/bancos/{banco_id}/auditoria"]
    assert set(caminho) == {"post", "get"}
    achado = aberto["components"]["schemas"]["AchadoResposta"]["properties"]
    assert set(achado) == {
        "risco",
        "alvo",
        "localizacao",
        "trecho_fonte",
        "proposta_ajuste",
    }
