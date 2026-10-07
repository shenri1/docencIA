from backend.app.api.deps import get_provedor_sob_demanda
from backend.app.main import app
from backend.app.models.identidade import SessaoGeracao
from backend.tests.conftest import _auth
from backend.tests.services.geracao.duplos import ProvedorLLMFake, corpo_questao
from backend.tests.services.orquestrador.test_orquestrador_service import (
    material_indexado,
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


def sessao_com_material(client, db_session, armazenamento, credencial):
    """Login, sessão e material já indexado. O envio multipart é e
    não passa pelo Orquestrador; aqui ele é o fixture."""
    headers = _auth(client, credencial)
    sessao_id = client.post("/sessoes", headers=headers, json=SESSAO).json()["id"]
    material_indexado(db_session, armazenamento, db_session.get(SessaoGeracao, sessao_id))
    return headers, sessao_id


def roteiro_com_subtemas(n: int) -> list[dict]:
    """Duas respostas por questão, subtema distinto por questão: com subtema
    igual em todas, a regra de sobreposição recusaria a montagem."""
    return [corpo_questao(5, subtema=f"s{q}") for q in range(n) for _ in range(2)]


def test_marco_sem_token_e_401(client):
    assert client.get("/sessoes/1/marco").status_code == 401
    assert client.post("/sessoes/1/comando", json={"comando": "prosseguir"}).status_code == 401


def test_marco_de_sessao_alheia_e_404(client, db_session, armazenamento):
    _, sessao_id = sessao_com_material(client, db_session, armazenamento, "orq-dono")
    outro = _auth(client, "orq-intruso")
    assert client.get(f"/sessoes/{sessao_id}/marco", headers=outro).status_code == 404


def test_marco_em_m1(client, db_session, armazenamento):
    headers, sessao_id = sessao_com_material(client, db_session, armazenamento, "orq-m1")
    corpo = client.get(f"/sessoes/{sessao_id}/marco", headers=headers).json()
    assert corpo["marco"] == "m1_materiais"
    assert corpo["n_materiais"] == 1
    assert corpo["comandos"] == ["prosseguir"]
    assert corpo["bancos"] == []


def test_comando_desconhecido_e_422(client, db_session, armazenamento):
    headers, sessao_id = sessao_com_material(client, db_session, armazenamento, "orq-422")
    resposta = client.post(
        f"/sessoes/{sessao_id}/comando", headers=headers, json={"comando": "parar"}
    )
    assert resposta.status_code == 422


def test_contagens_fora_do_limite_e_422(client, db_session, armazenamento):
    headers, sessao_id = sessao_com_material(client, db_session, armazenamento, "orq-n")
    for corpo in (
        {"comando": "prosseguir", "versao": "v1", "n_objetivas": 26, "n_discursivas": 0},
        {"comando": "prosseguir", "versao": "v1", "n_objetivas": 5},
    ):
        resposta = client.post(f"/sessoes/{sessao_id}/comando", headers=headers, json=corpo)
        assert resposta.status_code == 422


def test_campos_do_marco_e_422_com_o_codigo(client, db_session, armazenamento):
    headers, sessao_id = sessao_com_material(client, db_session, armazenamento, "orq-campos")
    resposta = client.post(
        f"/sessoes/{sessao_id}/comando",
        headers=headers,
        json={"comando": "prosseguir", "versao": "v1"},
    )
    assert resposta.status_code == 422
    assert resposta.json()["codigo"] == "CAMPOS_DO_MARCO"
    assert resposta.json()["sobrando"] == ["versao"]


def test_comando_fora_do_marco_e_409_com_o_codigo(client, db_session, armazenamento):
    headers, sessao_id = sessao_com_material(client, db_session, armazenamento, "orq-409")
    resposta = client.post(
        f"/sessoes/{sessao_id}/comando",
        headers=headers,
        json={"comando": "auditar", "versao": "v1"},
    )
    assert resposta.status_code == 409
    assert resposta.json()["codigo"] == "COMANDO_FORA_DO_MARCO"
    assert resposta.json()["comandos_aceitos"] == ["prosseguir"]


def test_f1_a_f12_so_por_comando(client, db_session, armazenamento):
    """Caminho feliz inteiro, depois de login, sessão e material. Também é o
    do login ao banco gerado são login, criar sessão, enviar o
    material, prosseguir no M1 e prosseguir no M2 — 5 requisições. O RNF fala
    em 50 questões; o limite do sistema é 25, e a contagem não depende de N."""
    headers, sessao_id = sessao_com_material(client, db_session, armazenamento, "orq-f1f12")
    url = f"/sessoes/{sessao_id}/comando"
    comandos = 0

    def comando(corpo):
        nonlocal comandos
        comandos += 1
        resposta = client.post(url, headers=headers, json=corpo)
        assert resposta.status_code == 200, resposta.json()
        return resposta.json()

    app.dependency_overrides[get_provedor_sob_demanda] = lambda: lambda: ProvedorLLMFake(
        roteiro_com_subtemas(25)
    )
    try:
        m1 = comando({"comando": "prosseguir"})
        assert m1["indice"]["confirmado"] is True
        assert m1["indice"]["materiais"][0]["identificador_curto"] == "P1"

        m2 = comando(
            {"comando": "prosseguir", "versao": "v1", "n_objetivas": 25, "n_discursivas": 0}
        )
    finally:
        app.dependency_overrides.pop(get_provedor_sob_demanda, None)
    assert m2["banco"]["geradas"] == 25
    assert comandos == 2  # as duas interações depois de sessão e material
    [banco] = m2["marco"]["bancos"]
    assert banco["marco"] == "m3_exclusoes"
    assert banco["lacunas"] == 0

    m3 = comando(
        {"comando": "prosseguir", "versao": "v1", "revisao_esperada": banco["revisao"]}
    )
    assert m3["relatorio"]["evento"] == "congelamento"
    assert len(m3["catalogo"]) == 25
    revisao = m3["marco"]["bancos"][0]["revisao"]

    m6 = comando(
        {
            "comando": "prosseguir",
            "versao": "v1",
            "revisao_esperada": revisao,
            "n_objetivas": 10,
            "n_discursivas": 0,
        }
    )
    assert m6["provas"]["verificacao"]["violacoes"] == []
    assert [g["modalidade"] for g in m6["gabaritos"]] == ["simples", "simples"]
    assert m6["marco"]["bancos"][0]["marco"] == "m10_docx"

    m10 = comando({"comando": "prosseguir", "versao": "v1", "revisao_esperada": revisao})
    assert sorted(e["tipo"] for e in m10["exportacoes"]) == ["conteudo_puro", "metadados"]
    assert all("caminho_arquivo" not in e for e in m10["exportacoes"])
    assert m10["marco"]["bancos"][0]["marco"] == "concluido"
