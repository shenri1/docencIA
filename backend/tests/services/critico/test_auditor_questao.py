from backend.app.domain import RiscoAuditoria
from backend.app.models.banco import Alternativa
from backend.app.services.calculo_distribuicao_service import calcular_distribuicao
from backend.app.services.critico.auditor_service import auditar_questao
from backend.tests.fabrica_banco import criar_banco, criar_questao_objetiva
from backend.tests.services.geracao.duplos import ProvedorLLMFake
from backend.tests.services.geracao.test_banco_service import preparar

DISTRIBUICAO = calcular_distribuicao(3, 30, 40, 30)


def sem_achado() -> dict:
    return {"achados": []}


def com_achado(localizacao: str, alvo: str = "C") -> dict:
    return {
        "achados": [
            {
                "risco": "correta_nao_unica",
                "alvo": alvo,
                "localizacao": localizacao,
                "trecho_fonte": "o material também sustenta essa leitura",
                "proposta_ajuste": "Reescreva a alternativa para não ser sustentável.",
            }
        ]
    }


def preparar_questao(db, armazenamento, sessao):
    preparar(db, armazenamento, sessao)
    banco = criar_banco(db, sessao, n_objetivas=3)
    questao = criar_questao_objetiva(db, banco, numero=1)
    db.commit()
    return questao


def auditar(db, emb, rer, provedor, sessao, questao):
    return auditar_questao(db, emb, rer, provedor, sessao, questao, DISTRIBUICAO)


def test_mensagem_traz_trechos_enunciado_alternativas_e_a_correta(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """Sem saber qual é a correta, o modelo não pode julgar se outra também é
    defensável."""
    questao = preparar_questao(db_session, armazenamento, sessao_rascunho)
    provedor = ProvedorLLMFake([sem_achado()])

    auditar(db_session, embeddings_fake, reranker_fake, provedor, sessao_rascunho, questao)

    usuario = provedor.requisicoes[0].usuario
    assert questao.enunciado in usuario
    assert "opção A" in usuario
    assert "Alternativa correta: A" in usuario
    assert "Trechos disponíveis" in usuario


def test_mensagem_nao_traz_as_violacoes_de_forma(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """Ao contrário da parte A: o auditor não corrige, e alimentá-lo com o que o
    código já mediu só duplicaria a lista."""
    questao = preparar_questao(db_session, armazenamento, sessao_rascunho)
    provedor = ProvedorLLMFake([sem_achado()])

    auditar(db_session, embeddings_fake, reranker_fake, provedor, sessao_rascunho, questao)

    usuario = provedor.requisicoes[0].usuario
    assert "Violações de forma" not in usuario
    assert "média das demais" not in usuario


def test_uma_chamada_por_questao(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    questao = preparar_questao(db_session, armazenamento, sessao_rascunho)
    provedor = ProvedorLLMFake([sem_achado()])
    auditar(db_session, embeddings_fake, reranker_fake, provedor, sessao_rascunho, questao)
    assert provedor.chamadas == 1


def test_lista_vazia_do_modelo_devolve_so_os_achados_de_forma(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    questao = preparar_questao(db_session, armazenamento, sessao_rascunho)
    resultado = auditar(
        db_session, embeddings_fake, reranker_fake,
        ProvedorLLMFake([sem_achado()]), sessao_rascunho, questao,
    )
    # A questão da fábrica é equilibrada: nenhum achado de forma tampouco.
    assert resultado.achados == []
    assert resultado.modelo == "fake"
    assert resultado.localizacoes


def _localizacao_enviada(db, emb, rer, sessao, questao) -> str:
    """A localização precisa ser uma das enviadas (o schema a fecha por enum);
    descobre-se qual com uma auditoria de sonda de lista vazia."""
    sonda = auditar(db, emb, rer, ProvedorLLMFake([sem_achado()]), sessao, questao)
    return sonda.localizacoes[0]


def test_achado_do_modelo_vira_achado_com_enum(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    questao = preparar_questao(db_session, armazenamento, sessao_rascunho)
    loc = _localizacao_enviada(
        db_session, embeddings_fake, reranker_fake, sessao_rascunho, questao
    )

    resultado = auditar(
        db_session, embeddings_fake, reranker_fake,
        ProvedorLLMFake([com_achado(loc)]), sessao_rascunho, questao,
    )

    assert len(resultado.achados) == 1
    achado = resultado.achados[0]
    assert achado.risco is RiscoAuditoria.CORRETA_NAO_UNICA
    assert achado.alvo == "C"
    assert achado.localizacao == loc


def test_achados_de_forma_vem_antes_dos_do_modelo(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """Ordem determinística, como na parte A: forma primeiro, depois o modelo em
    ordem de letra."""
    questao = preparar_questao(db_session, armazenamento, sessao_rascunho)
    longa = db_session.get(Alternativa, questao.alternativas[0].id)
    longa.texto = (
        "a fila preserva a ordem de descoberta dos vértices e garante visita por "
        "camadas de distância crescente a partir da origem escolhida"
    )
    db_session.commit()
    loc = _localizacao_enviada(
        db_session, embeddings_fake, reranker_fake, sessao_rascunho, questao
    )

    resultado = auditar(
        db_session, embeddings_fake, reranker_fake,
        ProvedorLLMFake([com_achado(loc)]), sessao_rascunho, questao,
    )
    assert resultado.achados[0].risco is RiscoAuditoria.ASSIMETRIA_FORMA
    assert resultado.achados[-1].risco is RiscoAuditoria.CORRETA_NAO_UNICA
