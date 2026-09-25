import pytest

from backend.app.domain import EstadoBanco, EstadoSessao, FaixaDificuldade
from backend.app.exceptions import (
    BancoCongeladoException,
    FonteInvalidaException,
    MaterialInsuficienteParaBancoException,
    PromptDivergenteException,
)
from backend.app.models.banco import (
    Alternativa,
    BancoQuestoes,
    FonteInterna,
    JustificativaEstruturada,
    Questao,
    RevisaoQuestao,
)
from backend.app.models.materiais import ChunkMaterial
from backend.app.prompt.parametros import ParametrosGeracao
from backend.app.services.geracao.banco_service import gerar_banco
from backend.app.services.prompt_mestre_service import ativar, registrar_versao
from backend.tests.services.geracao.duplos import (
    ProvedorLLMFake,
    corpo_insuficiencia,
    corpo_questao,
)
from backend.tests.services.rag.test_indexacao_service import criar_material

PARAMS_PROMPT = ParametrosGeracao(
    disciplina="Algoritmos",
    periodo="2026.2",
    area_do_conhecimento="Computação",
    tema_escopo="Grafos",
    k_alternativas=5,
    n_faceis=1,
    n_medias=2,
    n_dificeis=1,
)


def preparar(db, armazenamento, sessao, chunks: int = 20):
    """Prompt ativo, sessão confirmada e chunks suficientes para ancorar."""
    registrar_versao(db, "1.0.0", "docente", PARAMS_PROMPT)
    ativar(db, "1.0.0")
    material = criar_material(
        db, armazenamento, sessao, "P1", [("página 1", "conteúdo " * 40)]
    )
    db.query(ChunkMaterial).delete()
    for ordem in range(chunks):
        db.add(
            ChunkMaterial(
                material_id=material.id,
                ordem=ordem,
                texto=f"trecho numero {ordem} sobre busca em largura",
                localizacao=f"página {ordem + 1}",
                vetor_embedding=[0.0] * 1023 + [1.0],
            )
        )
    sessao.estado = EstadoSessao.MATERIAIS_CONFIRMADOS
    db.commit()


def roteiro(n: int, k: int = 5) -> list[dict]:
    """Duas respostas por questão: rascunho do Gerador e revisão do crítico."""
    return [corpo_questao(k) for _ in range(2 * n)]


def test_banco_respeita_a_distribuicao_por_faixa(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    # 10 questões com 30/40/30 -> 3 fáceis, 4 médias, 3 difíceis.
    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake(roteiro(10)),
        sessao_rascunho,
        n_alvo=10,
        versao="v1",
    )

    assert resumo.geradas == 10
    contagem = {
        faixa: db_session.query(Questao)
        .filter_by(banco_id=resumo.banco_id, faixa_dificuldade=faixa)
        .count()
        for faixa in FaixaDificuldade
    }
    assert contagem[FaixaDificuldade.FACIL] == 3
    assert contagem[FaixaDificuldade.MEDIA] == 4
    assert contagem[FaixaDificuldade.DIFICIL] == 3


def test_questao_persiste_com_alternativas_fontes_e_justificativa(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake(roteiro(2)),
        sessao_rascunho,
        n_alvo=2,
        versao="v1",
    )

    questao = db_session.query(Questao).filter_by(banco_id=resumo.banco_id).first()
    assert db_session.query(Alternativa).filter_by(questao_id=questao.id).count() == 5
    assert (
        db_session.query(Alternativa)
        .filter_by(questao_id=questao.id, correta=True)
        .count()
        == 1
    )
    assert db_session.query(FonteInterna).filter_by(questao_id=questao.id).count() >= 1
    justificativa = (
        db_session.query(JustificativaEstruturada).filter_by(questao_id=questao.id).one()
    )
    assert len(justificativa.invalidacao_distratores) == 4


def test_letras_sao_atribuidas_por_posicao_e_correta_segue_letra_correta(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake([corpo_questao(5, letra_correta="C")] * 2),
        sessao_rascunho,
        n_alvo=1,
        versao="v1",
    )

    questao = db_session.query(Questao).filter_by(banco_id=resumo.banco_id).one()
    alternativas = (
        db_session.query(Alternativa)
        .filter_by(questao_id=questao.id)
        .order_by(Alternativa.letra)
        .all()
    )
    assert [a.letra for a in alternativas] == ["A", "B", "C", "D", "E"]
    assert [a.texto for a in alternativas] == [f"opção {i}" for i in range(5)]
    assert [a.letra for a in alternativas if a.correta] == ["C"]
    assert [a.letra for a in alternativas if a.e_gemeo_malvado] == ["B"]


def test_insuficiencia_nao_aborta_o_banco(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    provedor = ProvedorLLMFake(
        [
            corpo_questao(5),
            corpo_questao(5),
            corpo_insuficiencia("faltou o critério"),
            corpo_questao(5),
            corpo_questao(5),
        ]
    )

    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        provedor,
        sessao_rascunho,
        n_alvo=3,
        versao="v1",
    )

    assert resumo.geradas == 2
    assert len(resumo.improdutivas) == 1
    assert "critério" in resumo.improdutivas[0].motivo
    assert resumo.improdutivas[0].numero == 2


def test_numeracao_e_sequencial_atraves_das_faixas(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """O plano concatena as faixas; a numeração tem que seguir contínua de 1 a
    n_alvo, sem repetir — `numero` é o índice da âncora e é unique por banco."""
    preparar(db_session, armazenamento, sessao_rascunho)
    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake(roteiro(10)),
        sessao_rascunho,
        n_alvo=10,
        versao="v1",
    )
    numeros = sorted(
        q.numero
        for q in db_session.query(Questao).filter_by(banco_id=resumo.banco_id).all()
    )
    assert numeros == list(range(1, 11))


def test_retomada_nao_regenera_o_que_ja_existe(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    primeiro = ProvedorLLMFake(roteiro(2))
    gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        primeiro,
        sessao_rascunho,
        n_alvo=2,
        versao="v1",
    )

    # Segunda chamada com n_alvo maior: só as duas novas devem ser geradas.
    segundo = ProvedorLLMFake(roteiro(4))
    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        segundo,
        sessao_rascunho,
        n_alvo=4,
        versao="v1",
    )

    assert resumo.ja_existentes == 2
    assert resumo.geradas == 2
    assert segundo.chamadas == 4
    numeros = [
        q.numero
        for q in db_session.query(Questao).filter_by(banco_id=resumo.banco_id).all()
    ]
    assert sorted(numeros) == [1, 2, 3, 4]
    assert len(numeros) == len(set(numeros))


def test_banco_congelado_falha_sem_chamar_o_modelo(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    banco = BancoQuestoes(
        sessao_id=sessao_rascunho.id,
        versao="v1",
        estado=EstadoBanco.CONGELADO,
        n_alvo=5,
        n_atual=0,
    )
    db_session.add(banco)
    db_session.commit()

    provedor = ProvedorLLMFake(roteiro(5))
    with pytest.raises(BancoCongeladoException):
        gerar_banco(
            db_session,
            embeddings_fake,
            reranker_fake,
            provedor,
            sessao_rascunho,
            n_alvo=5,
            versao="v1",
        )
    assert provedor.chamadas == 0


def test_material_insuficiente_falha_sem_chamar_o_modelo(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho, chunks=3)
    provedor = ProvedorLLMFake(roteiro(29))
    with pytest.raises(MaterialInsuficienteParaBancoException):
        gerar_banco(
            db_session,
            embeddings_fake,
            reranker_fake,
            provedor,
            sessao_rascunho,
            n_alvo=29,
            versao="v1",
        )
    assert provedor.chamadas == 0


def test_n_atual_reflete_o_que_foi_persistido(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake(
            [
                corpo_questao(5),
                corpo_questao(5),
                corpo_insuficiencia(),
                corpo_questao(5),
                corpo_questao(5),
            ]
        ),
        sessao_rascunho,
        n_alvo=3,
        versao="v1",
    )
    banco = db_session.get(BancoQuestoes, resumo.banco_id)
    assert banco.n_atual == 2
    assert banco.n_alvo == 3


LONGA = "opção com texto muito mais longo que todas as outras juntas somadas"


def alternativas(textos: list[str], gemeo: int = 1) -> list[dict]:
    return [{"texto": t, "e_gemeo_malvado": i == gemeo} for i, t in enumerate(textos)]


CURTAS = [f"opção {i}" for i in range(5)]
COM_LONGA = [CURTAS[0], CURTAS[1], LONGA, CURTAS[3], CURTAS[4]]


def gerar(db, emb, rer, sessao, provedor, n_alvo=1):
    return gerar_banco(db, emb, rer, provedor, sessao, n_alvo=n_alvo, versao="v1")


def test_cada_questao_custa_duas_chamadas(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    provedor = ProvedorLLMFake(roteiro(3))
    resumo = gerar(
        db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor, 3
    )
    assert resumo.geradas == 3
    assert provedor.chamadas == 6


def test_revisao_persistida_com_rascunho_e_violacoes(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    rascunho = corpo_questao(
        5, enunciado="Rascunho?", alternativas=alternativas(COM_LONGA)
    )
    provedor = ProvedorLLMFake([rascunho, corpo_questao(5)])
    resumo = gerar(db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor)

    questao = db_session.query(Questao).filter_by(banco_id=resumo.banco_id).one()
    revisao = db_session.query(RevisaoQuestao).filter_by(questao_id=questao.id).one()
    assert revisao.rascunho["enunciado"] == "Rascunho?"
    assert [v["regra"] for v in revisao.violacoes_rascunho] == ["tamanho_alternativa"]
    assert revisao.violacoes_rascunho[0]["alvo"] == "C"
    assert revisao.violacoes_final == []
    assert revisao.modelo_geracao == "fake"
    assert revisao.modelo_revisao == "fake"
    # O que vai para Questao é a versão revisada.
    assert questao.enunciado == corpo_questao(5)["resultado"]["enunciado"]
    assert resumo.com_violacoes == []


def test_violacoes_do_rascunho_chegam_ao_critico(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    rascunho = corpo_questao(5, alternativas=alternativas(COM_LONGA))
    provedor = ProvedorLLMFake([rascunho, corpo_questao(5)])
    gerar(db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor)
    assert "tamanho_alternativa" in provedor.requisicoes[1].usuario


def test_revisao_que_nao_corrige_mantem_a_violacao(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    ruim = corpo_questao(5, alternativas=alternativas(COM_LONGA))
    resumo = gerar(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake([ruim, ruim]),
    )
    revisao = db_session.query(RevisaoQuestao).one()
    assert [v["regra"] for v in revisao.violacoes_final] == ["tamanho_alternativa"]
    assert [item.numero for item in resumo.com_violacoes] == [1]
    assert resumo.com_violacoes[0].violacoes[0].alvo == "C"


def test_fonte_persistida_vem_da_revisao_mesmo_com_rascunho_invalido(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """Só a revisada vira FonteInterna. Um P9 no rascunho que o crítico corrige
    não pode derrubar a questão."""
    preparar(db_session, armazenamento, sessao_rascunho)
    revisada = corpo_questao(
        5,
        fontes=[
            {
                "identificador_material": "P1",
                "localizacao": "página 77",
                "trecho_base": "Trecho citado pela revisão.",
            }
        ],
    )
    provedor = ProvedorLLMFake([corpo_questao(5, identificador="P9"), revisada])
    resumo = gerar(db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor)

    questao = db_session.query(Questao).filter_by(banco_id=resumo.banco_id).one()
    fonte = db_session.query(FonteInterna).filter_by(questao_id=questao.id).one()
    assert fonte.localizacao == "página 77"
    assert fonte.trecho_base == "Trecho citado pela revisão."


def test_fonte_inventada_na_revisao_e_rejeitada_sem_persistir(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    provedor = ProvedorLLMFake([corpo_questao(5), corpo_questao(5, identificador="P9")])
    with pytest.raises(FonteInvalidaException):
        gerar(db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor)
    assert not db_session.new
    db_session.rollback()
    assert db_session.query(Questao).count() == 0
    assert db_session.query(RevisaoQuestao).count() == 0


def test_insuficiencia_declarada_pelo_critico_vira_improdutiva(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    provedor = ProvedorLLMFake(
        [corpo_questao(5), corpo_insuficiencia("o trecho não define o critério")]
    )
    resumo = gerar(db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor)
    assert resumo.geradas == 0
    assert resumo.improdutivas[0].motivo == "revisão: o trecho não define o critério"
    assert db_session.query(Questao).count() == 0


def test_ancora_recusada_pelo_critico_e_tentada_de_novo_na_retomada(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    gerar(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake([corpo_questao(5), corpo_insuficiencia()]),
    )
    resumo = gerar(
        db_session, embeddings_fake, reranker_fake, sessao_rascunho, ProvedorLLMFake(roteiro(1))
    )
    assert resumo.ja_existentes == 0
    assert resumo.geradas == 1


def test_prompt_do_critico_editado_sem_versao_bloqueia_antes_do_modelo(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho, monkeypatch
):
    from backend.app.prompt import montagem
    from backend.app.services import prompt_mestre_service

    preparar(db_session, armazenamento, sessao_rascunho)
    monkeypatch.setattr(
        prompt_mestre_service,
        "carregar_modulos_versionados",
        lambda: montagem.carregar_modulos() + [("critico/01_revisor.md", "editado")],
    )
    provedor = ProvedorLLMFake(roteiro(1))
    with pytest.raises(PromptDivergenteException):
        gerar(db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor)
    assert provedor.chamadas == 0
