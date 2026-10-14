import pytest

from backend.app.domain import EstadoBanco, EstadoProva
from backend.app.exceptions import InconsistenciaDeEstadoException
from backend.app.services.exportacao.consistencia import verificar_exportavel
from backend.tests.services.provas.test_gabarito import item_da_prova, provas_montadas


def problemas_de(db, docente, banco) -> list[str]:
    with pytest.raises(InconsistenciaDeEstadoException) as erro:
        verificar_exportavel(db, docente, banco)
    return erro.value.extras["problemas"]


def test_estado_coerente_devolve_o_par(db_session, docente, sessao_rascunho):
    banco, montadas = provas_montadas(db_session, docente, sessao_rascunho)
    a, b = verificar_exportavel(db_session, docente, banco)
    assert (a.id, b.id) == (montadas.prova_a_id, montadas.prova_b_id)


def test_banco_aberto_e_problema(db_session, docente, sessao_rascunho):
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    banco.estado = EstadoBanco.ABERTO
    db_session.commit()
    assert any("congelado" in p for p in problemas_de(db_session, docente, banco))


def test_problema_de_consistencia_do_banco_entra_na_lista(
    db_session, docente, sessao_rascunho
):
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    banco.n_atual = 99
    db_session.commit()
    assert any("n_atual" in p for p in problemas_de(db_session, docente, banco))


def test_prova_desatualizada_bloqueia(db_session, docente, sessao_rascunho):
    """ deixaram para cá: leitura e gabarito marcam, a exportação
    bloqueia."""
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    banco.revisao += 1
    db_session.commit()
    assert any("desatualizada" in p for p in problemas_de(db_session, docente, banco))


def test_prova_nao_montada_e_problema(db_session, docente, sessao_rascunho):
    banco, montadas = provas_montadas(db_session, docente, sessao_rascunho)
    from backend.app.models.provas import Prova

    db_session.get(Prova, montadas.prova_a_id).estado = EstadoProva.RASCUNHO
    db_session.commit()
    assert any("montada" in p for p in problemas_de(db_session, docente, banco))


def test_violacao_de_verificacao_bloqueia(db_session, docente, sessao_rascunho):
    banco, montadas = provas_montadas(db_session, docente, sessao_rascunho)
    item = item_da_prova(db_session, montadas.prova_a_id, 1)
    # Troca a correta de lugar com a vizinha. Inverter a lista inteira deixava
    # a correta quieta quando ela estava no meio, e o teste passava a depender
    # da semente (que muda com o id da sessão).
    ordem = list(item.ordem_alternativas)
    correta = next(a.letra for a in item.questao.alternativas if a.correta)
    i = ordem.index(correta)
    j = (i + 1) % len(ordem)
    ordem[i], ordem[j] = ordem[j], ordem[i]
    item.ordem_alternativas = ordem
    db_session.commit()
    assert problemas_de(db_session, docente, banco)


def test_gabarito_incompleto_bloqueia(db_session, docente, sessao_rascunho):
    banco, montadas = provas_montadas(db_session, docente, sessao_rascunho)
    item = item_da_prova(db_session, montadas.prova_a_id, 3)
    item.questao.justificativa.justificativa_correta = None
    db_session.commit()
    assert any("gabarito A" in p for p in problemas_de(db_session, docente, banco))


def test_sem_provas_montadas_e_problema(db_session, docente, sessao_rascunho):
    from backend.app.domain import FaixaDificuldade
    from backend.tests.fabrica_banco import criar_banco, criar_questao_objetiva

    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=1)
    criar_questao_objetiva(db_session, banco, numero=1, faixa=FaixaDificuldade.MEDIA)
    banco.estado = EstadoBanco.CONGELADO
    db_session.commit()
    assert any(
        "não foram montadas" in p for p in problemas_de(db_session, docente, banco)
    )


def test_varios_problemas_saem_juntos(db_session, docente, sessao_rascunho):
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    banco.estado = EstadoBanco.ABERTO
    banco.revisao += 1
    db_session.commit()
    assert len(problemas_de(db_session, docente, banco)) >= 2
