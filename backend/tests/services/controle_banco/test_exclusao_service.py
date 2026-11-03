import pytest

from backend.app.domain import (
    EstadoBanco,
    EstadoQuestao,
    EstadoSessao,
    EventoBanco,
    FaixaDificuldade,
)
from backend.app.exceptions import (
    BancoCongeladoException,
    BancoVazioException,
    InconsistenciaDeEstadoException,
    JanelaExclusoesFechadaException,
    NumerosInvalidosException,
    RevisaoDesatualizadaException,
)
from backend.app.models.banco import RegistroExclusao, RelatorioImpacto
from backend.app.services.controle_banco.exclusao_service import (
    congelar_banco,
    excluir_questoes,
)
from backend.tests.fabrica_banco import criar_banco, criar_questao_objetiva


def banco_com_dez(db, sessao):
    banco = criar_banco(db, sessao, n_objetivas=10)
    numero = 0
    for faixa, quantidade in (
        (FaixaDificuldade.FACIL, 3),
        (FaixaDificuldade.MEDIA, 4),
        (FaixaDificuldade.DIFICIL, 3),
    ):
        for _ in range(quantidade):
            numero += 1
            criar_questao_objetiva(db, banco, numero=numero, faixa=faixa)
    db.commit()
    return banco


def test_exclusao_marca_mantem_numero_e_registra(db_session, docente, sessao_rascunho):
    """Marca EXCLUIDA, mantém a numeração original, sem substituição
    automática."""
    banco = banco_com_dez(db_session, sessao_rascunho)
    relatorio = excluir_questoes(db_session, docente, banco, [2, 5], 0)

    excluidas = [q for q in banco.questoes if q.estado is EstadoQuestao.EXCLUIDA]
    assert sorted(q.numero for q in excluidas) == [2, 5]
    assert sorted(q.numero for q in banco.questoes) == list(range(1, 11))
    assert banco.n_atual == 8
    assert banco.revisao == 1
    assert relatorio.revisao == 1
    assert relatorio.evento is EventoBanco.EXCLUSAO
    assert relatorio.n_final == 8
    assert db_session.query(RegistroExclusao).count() == 2


def test_cada_rodada_de_exclusao_gera_um_relatorio(
    db_session, docente, sessao_rascunho
):
    """ Diz "após cada exclusão", e segue o RF em vez do passo
    único do F6."""
    banco = banco_com_dez(db_session, sessao_rascunho)
    excluir_questoes(db_session, docente, banco, [1], 0)
    excluir_questoes(db_session, docente, banco, [2], 1)
    assert banco.revisao == 2
    assert db_session.query(RelatorioImpacto).count() == 2


def test_um_numero_invalido_nao_exclui_nenhum(db_session, docente, sessao_rascunho):
    banco = banco_com_dez(db_session, sessao_rascunho)
    with pytest.raises(NumerosInvalidosException) as erro:
        excluir_questoes(db_session, docente, banco, [3, 99], 0)
    assert erro.value.extras["invalidos"] == [
        {"numero": 99, "motivo": "não existe ou não está ativa no banco"}
    ]
    # "Nenhum" é sobre o gravado: desfaz a transação, como o handler, e relê.
    db_session.rollback()
    db_session.expire_all()
    assert [q.estado for q in banco.questoes] == [EstadoQuestao.ATIVA] * 10
    assert banco.n_atual == 10
    assert banco.revisao == 0
    assert db_session.query(RegistroExclusao).count() == 0


def test_numero_repetido_na_lista_e_invalido(db_session, docente, sessao_rascunho):
    banco = banco_com_dez(db_session, sessao_rascunho)
    with pytest.raises(NumerosInvalidosException) as erro:
        excluir_questoes(db_session, docente, banco, [3, 3], 0)
    assert erro.value.extras["invalidos"][0]["motivo"] == "repetido na lista"


def test_excluir_questao_ja_excluida_e_invalido(db_session, docente, sessao_rascunho):
    banco = banco_com_dez(db_session, sessao_rascunho)
    excluir_questoes(db_session, docente, banco, [4], 0)
    with pytest.raises(NumerosInvalidosException):
        excluir_questoes(db_session, docente, banco, [4], 1)


def test_revisao_desatualizada_recusa_a_exclusao(db_session, docente, sessao_rascunho):
    banco = banco_com_dez(db_session, sessao_rascunho)
    excluir_questoes(db_session, docente, banco, [1], 0)
    with pytest.raises(RevisaoDesatualizadaException):
        excluir_questoes(db_session, docente, banco, [2], 0)
    assert banco.n_atual == 9


def test_exclusao_em_banco_congelado_responde_409(db_session, docente, sessao_rascunho):
    banco = banco_com_dez(db_session, sessao_rascunho)
    congelar_banco(db_session, docente, banco, 0)
    with pytest.raises(JanelaExclusoesFechadaException):
        excluir_questoes(db_session, docente, banco, [1], 1)


def test_congelar_move_banco_e_sessao_e_grava_relatorio(
    db_session, docente, sessao_rascunho
):
    banco = banco_com_dez(db_session, sessao_rascunho)
    relatorio = congelar_banco(db_session, docente, banco, 0)
    assert banco.estado is EstadoBanco.CONGELADO
    assert banco.sessao.estado is EstadoSessao.BANCO_CONGELADO
    assert relatorio.evento is EventoBanco.CONGELAMENTO
    assert banco.revisao == 1


def test_congelar_duas_vezes_responde_409(db_session, docente, sessao_rascunho):
    banco = banco_com_dez(db_session, sessao_rascunho)
    congelar_banco(db_session, docente, banco, 0)
    with pytest.raises(BancoCongeladoException):
        congelar_banco(db_session, docente, banco, 1)


def test_congelar_banco_sem_questao_ativa_responde_409(
    db_session, docente, sessao_rascunho
):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=1)
    db_session.commit()
    with pytest.raises(BancoVazioException):
        congelar_banco(db_session, docente, banco, 0)


def test_congelar_banco_incoerente_responde_409(db_session, docente, sessao_rascunho):
    banco = banco_com_dez(db_session, sessao_rascunho)
    banco.n_atual = 99
    db_session.commit()
    with pytest.raises(InconsistenciaDeEstadoException):
        congelar_banco(db_session, docente, banco, 0)
    assert banco.estado is EstadoBanco.ABERTO
