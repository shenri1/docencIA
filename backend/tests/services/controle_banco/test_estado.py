import pytest

from backend.app.domain import EstadoQuestao, EventoBanco, FaixaDificuldade
from backend.app.exceptions import (
    BancoNaoEncontradoException,
    RevisaoDesatualizadaException,
)
from backend.app.models.banco import RelatorioImpacto
from backend.app.schemas.identidade import DocenteCriar
from backend.app.services.auth_service import registrar_docente
from backend.app.services.controle_banco.estado import (
    exigir_revisao,
    obter_banco,
    registrar_relatorio,
)
from backend.tests.fabrica_banco import (
    criar_banco,
    criar_questao_discursiva,
    criar_questao_objetiva,
)


def test_obter_banco_devolve_o_banco_do_docente(db_session, docente, sessao_rascunho):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=3)
    db_session.commit()
    assert obter_banco(db_session, docente, banco.id).id == banco.id


def test_obter_banco_de_outro_docente_responde_404(
    db_session, docente, sessao_rascunho
):
    """404 e não 403: 403 confirmaria que o banco existe."""
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=3)
    db_session.commit()
    outro = registrar_docente(
        db_session,
        DocenteCriar(
            nome="Bruno", credencial_institucional="prof-outro", senha="senhaforte123"
        ),
    )
    with pytest.raises(BancoNaoEncontradoException):
        obter_banco(db_session, outro, banco.id)


def test_obter_banco_inexistente_responde_404(db_session, docente):
    with pytest.raises(BancoNaoEncontradoException):
        obter_banco(db_session, docente, 987654)


def test_exigir_revisao_aceita_a_revisao_atual(db_session, sessao_rascunho):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=3)
    exigir_revisao(banco, 0)  # não levanta


def test_exigir_revisao_recusa_revisao_diferente(db_session, sessao_rascunho):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=3)
    banco.revisao = 2
    with pytest.raises(RevisaoDesatualizadaException) as erro:
        exigir_revisao(banco, 1)
    assert erro.value.extras["revisao_atual"] == 2
    assert erro.value.extras["revisao_esperada"] == 1


def test_registrar_relatorio_incrementa_revisao_e_conta_so_as_ativas(
    db_session, sessao_rascunho
):
    """sessao_rascunho é 30/40/30. 3 fáceis, 4 médias, 3 difíceis ativas mais
    uma excluída: a excluída não entra na contagem."""
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=11)
    numero = 0
    for faixa, quantidade in (
        (FaixaDificuldade.FACIL, 3),
        (FaixaDificuldade.MEDIA, 4),
        (FaixaDificuldade.DIFICIL, 3),
    ):
        for _ in range(quantidade):
            numero += 1
            criar_questao_objetiva(db_session, banco, numero=numero, faixa=faixa)
    criar_questao_objetiva(
        db_session,
        banco,
        numero=11,
        faixa=FaixaDificuldade.FACIL,
        estado=EstadoQuestao.EXCLUIDA,
    )
    db_session.commit()

    relatorio = registrar_relatorio(db_session, banco, EventoBanco.EXCLUSAO)
    db_session.commit()

    assert banco.revisao == 1
    assert relatorio.revisao == 1
    assert relatorio.evento is EventoBanco.EXCLUSAO
    assert relatorio.n_final == 10
    assert relatorio.contagem_por_faixa == {
        "objetiva": {"facil": 3, "media": 4, "dificil": 3}
    }
    # Texto, não Decimal nem float: JSONB não serializa Decimal.
    assert relatorio.desvio_observado == {
        "objetiva": {"facil": "0.00", "media": "0.00", "dificil": "0.00"}
    }
    assert relatorio.alerta_desvio is False


def test_registrar_relatorio_de_banco_misto_separa_por_tipo(
    db_session, sessao_rascunho
):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=2, n_discursivas=1)
    criar_questao_objetiva(db_session, banco, numero=1, faixa=FaixaDificuldade.FACIL)
    criar_questao_objetiva(db_session, banco, numero=2, faixa=FaixaDificuldade.MEDIA)
    criar_questao_discursiva(
        db_session, banco, numero=3, faixa=FaixaDificuldade.DIFICIL
    )
    db_session.commit()

    relatorio = registrar_relatorio(db_session, banco, EventoBanco.CONGELAMENTO)
    db_session.commit()

    assert set(relatorio.contagem_por_faixa) == {"objetiva", "discursiva"}
    assert relatorio.contagem_por_faixa["discursiva"] == {
        "facil": 0,
        "media": 0,
        "dificil": 1,
    }
    # N pequeno: o desvio estoura 5 pontos sozinho, e isso é declarado.
    assert relatorio.alerta_desvio is True


def test_registrar_relatorio_nao_faz_commit(db_session, sessao_rascunho):
    """Sempre roda dentro da transação da mudança que o motivou: um rollback
    depois dele tem de desfazer o relatório e a revisão."""
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=1)
    criar_questao_objetiva(db_session, banco, numero=1)
    db_session.commit()

    registrar_relatorio(db_session, banco, EventoBanco.EXCLUSAO)
    db_session.rollback()

    db_session.refresh(banco)
    assert banco.revisao == 0
    assert db_session.query(RelatorioImpacto).count() == 0
