"""O que o `banco_service` não cobre: a substituição e a repetida."""

from sqlalchemy import select

from backend.app.domain import EstadoQuestao, TipoQuestao
from backend.app.models.metricas import MetricaGeracao
from backend.app.services.geracao.ancoras import selecionar_ancoras
from backend.app.services.geracao.banco_service import (
    Improdutiva,
    _montar_plano,
    _obter_ou_criar_banco,
    produzir_questao,
)
from backend.app.services.metricas.juiz import JuizFake
from backend.tests.services.geracao.duplos import ProvedorLLMFake, corpo_questao
from backend.tests.services.geracao.test_banco_service import preparar


def _produzir(db, emb, rer, sessao, roteiro_, **extra):
    banco = _obter_ou_criar_banco(db, sessao, "v1", 10, 0)
    item = _montar_plano(sessao, 10, 0)[0]
    return produzir_questao(
        db,
        emb,
        rer,
        ProvedorLLMFake(roteiro_),
        sessao,
        banco,
        1,
        TipoQuestao.OBJETIVA,
        item.faixa,
        selecionar_ancoras(db, sessao, 10)[0],
        item.distribuicao,
        juiz=JuizFake(),
        **extra,
    )


def _linhas(db) -> list[MetricaGeracao]:
    return list(db.scalars(select(MetricaGeracao).order_by(MetricaGeracao.id)))


def test_candidata_grava_origem_substituicao(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    _produzir(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        [corpo_questao(5), corpo_questao(5)],
        estado=EstadoQuestao.CANDIDATA,
    )
    [linha] = _linhas(db_session)
    assert linha.origem == "substituicao"
    assert linha.desfecho == "produzida"


def test_rascunho_repetido_grava_desfecho_repetida(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    produzida = _produzir(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        [corpo_questao(5)],
        estado=EstadoQuestao.CANDIDATA,
        pergunta_original="Qual estrutura a busca em largura utiliza?",
    )
    assert isinstance(produzida, Improdutiva) and produzida.repetida
    [linha] = _linhas(db_session)
    assert linha.desfecho == "repetida"
    assert linha.origem == "substituicao"
    assert linha.questao_id is None
