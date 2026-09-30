import pytest
from sqlalchemy import select

from backend.app.domain import (
    DecisaoSubstituicao,
    EstadoBanco,
    EstadoProva,
    EstadoQuestao,
    EventoBanco,
    FaixaDificuldade,
    TipoQuestao,
)
from backend.app.exceptions import (
    CandidataPendenteException,
    EstadoQuestaoInvalidoException,
    QuestaoNaoEncontradaException,
    RevisaoDesatualizadaException,
    SemCandidataPendenteException,
    SubstituicaoAposMontagemException,
)
from backend.app.models.banco import BancoQuestoes, Questao, RegistroSubstituicao
from backend.app.models.provas import Prova
from backend.app.services.controle_banco import substituicao_service
from backend.app.services.controle_banco.exclusao_service import (
    congelar_banco,
    excluir_questoes,
)
from backend.app.services.controle_banco.substituicao_service import (
    aceitar_substituicao,
    propor_substituicao,
    rejeitar_substituicao,
)
from backend.app.services.geracao.banco_service import Improdutiva, gerar_banco
from backend.tests.travamento import espiar_lock
from backend.tests.services.geracao.duplos import (
    ProvedorLLMFake,
    corpo_insuficiencia,
)
from backend.tests.services.geracao.test_banco_service import preparar, roteiro


def banco_gerado(db, armazenamento, embeddings, reranker, sessao, n=3):
    """Banco real, pelo laço /10: a substituição precisa das âncoras
    determinísticas, que só existem sobre material indexado."""
    preparar(db, armazenamento, sessao)
    resumo = gerar_banco(
        db,
        embeddings,
        reranker,
        ProvedorLLMFake(roteiro(n)),
        sessao,
        n_objetivas=n,
        n_discursivas=0,
        versao="v1",
    )
    return db.get(BancoQuestoes, resumo.banco_id)


def _propor(db, emb, rer, docente, banco, numero, roteiro_=None):
    return propor_substituicao(
        db, emb, rer, ProvedorLLMFake(roteiro_ or roteiro(1)), docente, banco, numero
    )


def test_propor_nao_altera_o_banco(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    revisao_antes, n_antes = banco.revisao, banco.n_atual
    original = next(q for q in banco.questoes if q.numero == 2)

    produzida = _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 2)

    assert produzida.questao.estado is EstadoQuestao.CANDIDATA
    assert produzida.questao.numero == 2
    assert produzida.questao.tipo is TipoQuestao.OBJETIVA
    assert original.estado is EstadoQuestao.ATIVA
    assert (banco.revisao, banco.n_atual) == (revisao_antes, n_antes)


def test_propor_manda_o_enunciado_da_original_como_evitar(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    original = next(q for q in banco.questoes if q.numero == 1)
    provedor = ProvedorLLMFake(roteiro(1))

    propor_substituicao(
        db_session, embeddings_fake, reranker_fake, provedor, docente, banco, 1
    )

    usuario = provedor.requisicoes[0].usuario
    assert original.enunciado in usuario
    # Objetiva manda também as alternativas: o docente não quer a mesma questão
    # com as mesmas opções em outra ordem.
    assert original.alternativas[0].texto in usuario


def test_aceitar_troca_no_mesmo_numero_e_preserva_a_original(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    original = next(q for q in banco.questoes if q.numero == 2)
    candidata = _propor(
        db_session, embeddings_fake, reranker_fake, docente, banco, 2
    ).questao

    relatorio = aceitar_substituicao(db_session, docente, banco, 2, banco.revisao)

    assert original.estado is EstadoQuestao.SUBSTITUIDA
    assert candidata.estado is EstadoQuestao.ATIVA
    assert candidata.numero == 2
    assert banco.n_atual == 3  # a original já era ativa: a contagem não muda
    assert relatorio.evento is EventoBanco.SUBSTITUICAO
    assert banco.revisao == relatorio.revisao
    registro = db_session.query(RegistroSubstituicao).one()
    assert registro.decisao is DecisaoSubstituicao.ACEITA
    assert (registro.questao_original_id, registro.candidata_id) == (
        original.id,
        candidata.id,
    )


def test_aceitar_substituicao_de_questao_excluida_recoloca_no_banco(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """ "Excluí a Q2 e agora quero outra no lugar" é o reequilíbrio manual."""
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    excluir_questoes(db_session, docente, banco, [2], banco.revisao)
    assert banco.n_atual == 2

    _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 2)
    aceitar_substituicao(db_session, docente, banco, 2, banco.revisao)
    assert banco.n_atual == 3


def test_rejeitar_descarta_sem_mexer_no_banco(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    revisao_antes = banco.revisao
    produzida = _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 3)

    descartada = rejeitar_substituicao(db_session, docente, banco, 3)

    assert descartada.id == produzida.questao.id
    assert descartada.estado is EstadoQuestao.DESCARTADA
    assert banco.revisao == revisao_antes
    assert db_session.query(RegistroSubstituicao).one().decisao is (
        DecisaoSubstituicao.REJEITADA
    )


def test_depois_de_rejeitar_pode_propor_de_novo(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)
    rejeitar_substituicao(db_session, docente, banco, 1)
    segunda = _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)
    assert segunda.questao.estado is EstadoQuestao.CANDIDATA


def test_propor_com_candidata_pendente_responde_409(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)
    with pytest.raises(CandidataPendenteException):
        _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)


def test_propor_numero_inexistente_responde_404(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    with pytest.raises(QuestaoNaoEncontradaException):
        _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 99)


def test_propor_substituicao_de_questao_substituida_responde_409(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)
    aceitar_substituicao(db_session, docente, banco, 1, banco.revisao)
    # A original agora é SUBSTITUIDA. Propor de novo atinge a ATIVA nova, o que
    # é permitido; o que não pode é mirar a linha substituída.
    substituida = db_session.scalars(
        select(Questao).where(
            Questao.banco_id == banco.id,
            Questao.estado == EstadoQuestao.SUBSTITUIDA,
        )
    ).one()
    substituida.numero = 98
    db_session.commit()
    with pytest.raises(EstadoQuestaoInvalidoException):
        _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 98)


def test_insuficiencia_na_proposta_nao_persiste_nada(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    antes = db_session.query(Questao).count()
    resultado = _propor(
        db_session,
        embeddings_fake,
        reranker_fake,
        docente,
        banco,
        1,
        [corpo_insuficiencia("o trecho não sustenta outra questão")],
    )
    assert isinstance(resultado, Improdutiva)
    assert db_session.query(Questao).count() == antes


def test_aceitar_sem_candidata_responde_409(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    with pytest.raises(SemCandidataPendenteException):
        aceitar_substituicao(db_session, docente, banco, 1, banco.revisao)


def test_rejeitar_sem_candidata_responde_409(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    with pytest.raises(SemCandidataPendenteException):
        rejeitar_substituicao(db_session, docente, banco, 1)


def test_aceitar_com_revisao_desatualizada_responde_409(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)
    with pytest.raises(RevisaoDesatualizadaException):
        aceitar_substituicao(db_session, docente, banco, 1, banco.revisao + 5)


def test_substituicao_funciona_com_banco_congelado(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """o congelamento fecha a janela de exclusões, não a substituição
    com comando explícito. É por aqui que as propostas da auditoria (
    parte B) viram ação."""
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    congelar_banco(db_session, docente, banco, banco.revisao)
    assert banco.estado is EstadoBanco.CONGELADO

    _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)
    relatorio = aceitar_substituicao(db_session, docente, banco, 1, banco.revisao)
    assert relatorio.evento is EventoBanco.SUBSTITUICAO
    assert banco.estado is EstadoBanco.CONGELADO


def test_candidata_usa_a_mesma_faixa_da_original(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    original = next(q for q in banco.questoes if q.numero == 3)
    produzida = _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 3)
    assert produzida.questao.faixa_dificuldade is original.faixa_dificuldade
    assert isinstance(original.faixa_dificuldade, FaixaDificuldade)


def test_duas_substituicoes_do_mesmo_numero(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """Duas SUBSTITUIDA no número 1 é o caso normal, e é por isso que o índice
    é parcial em vez de UniqueConstraint(banco_id, numero)."""
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    for _ in range(2):
        _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)
        aceitar_substituicao(db_session, docente, banco, 1, banco.revisao)

    do_numero_1 = [q for q in banco.questoes if q.numero == 1]
    estados = sorted(q.estado.value for q in do_numero_1)
    assert estados == ["ativa", "substituida", "substituida"]
    assert banco.n_atual == 3


def test_aceitar_com_provas_montadas_responde_409_e_nao_muda_nada(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """Achado 5: aceitar move a revisão do banco; as provas já montadas ficam
    na revisão antiga, a exportação bloqueia para sempre e remontar não existe."""
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    produzida = _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)
    congelar_banco(db_session, docente, banco, banco.revisao)
    db_session.add(
        Prova(
            sessao_id=banco.sessao_id,
            banco_id=banco.id,
            versao="A",
            n_questoes=3,
            n_objetivas=3,
            n_discursivas=0,
            revisao_banco=banco.revisao,
            estado=EstadoProva.MONTADA,
        )
    )
    db_session.commit()
    revisao_antes = banco.revisao

    with pytest.raises(SubstituicaoAposMontagemException) as erro:
        aceitar_substituicao(db_session, docente, banco, 1, banco.revisao)

    assert erro.value.status_code == 409
    assert banco.revisao == revisao_antes
    assert produzida.questao.estado is EstadoQuestao.CANDIDATA


def test_aceitar_segura_o_lock_da_linha_do_banco(
    db_session,
    docente,
    armazenamento,
    embeddings_fake,
    reranker_fake,
    sessao_rascunho,
    engine,
    monkeypatch,
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)
    achados = espiar_lock(
        monkeypatch, substituicao_service, "registrar_relatorio", engine, banco.id
    )

    aceitar_substituicao(db_session, docente, banco, 1, banco.revisao)

    assert achados == [False]
