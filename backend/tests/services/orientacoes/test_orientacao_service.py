import pytest
from sqlalchemy import select

from backend.app.domain import EstadoOrientacao, OrigemOrientacao, TipoEventoAuditoria
from backend.app.exceptions import (
    EstadoOrientacaoInvalidoException,
    LimiteOrientacoesException,
    OrientacaoNaoEncontradaException,
)
from backend.app.models.auditoria import RegistroAuditoria
from backend.app.services.orientacoes import orientacao_service
from backend.app.services.orientacoes.orientacao_service import (
    criar_orientacao_questao,
    criar_orientacao_sessao,
    desativar,
    listar,
    registrar_iniciais,
    vigentes,
)
from backend.tests.fabrica_banco import criar_banco
from backend.tests.travamento import linha_esta_livre


def _de_sessao(db, docente, sessao, n):
    return [
        criar_orientacao_sessao(db, docente, sessao, f"orientação {i}")
        for i in range(n)
    ]


def _cruzada(db, docente, banco, numero, acumular=True):
    return criar_orientacao_questao(
        db, docente, banco, numero, "arquitetura de computadores", None, acumular
    )


def test_cria_orientacao_de_sessao_ativa(db_session, docente, sessao_rascunho):
    orientacao = criar_orientacao_sessao(
        db_session, docente, sessao_rascunho, "prefiro exemplos práticos"
    )
    assert orientacao.origem is OrigemOrientacao.SESSAO
    assert orientacao.estado is EstadoOrientacao.ATIVA
    assert (orientacao.banco_id, orientacao.numero_origem, orientacao.cruzar_com) == (
        None,
        None,
        None,
    )


def test_sexta_ativa_e_recusada(db_session, docente, sessao_rascunho):
    _de_sessao(db_session, docente, sessao_rascunho, 5)
    with pytest.raises(LimiteOrientacoesException) as exc:
        criar_orientacao_sessao(db_session, docente, sessao_rascunho, "mais uma")
    assert exc.value.extras["ativas"] == 5
    assert exc.value.extras["teto_ativas"] == 5


def test_terceira_com_cruzamento_e_recusada_mas_sem_cruzamento_cabe(
    db_session, docente, sessao_rascunho
):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=3)
    _cruzada(db_session, docente, banco, 1)
    _cruzada(db_session, docente, banco, 2)
    with pytest.raises(LimiteOrientacoesException) as exc:
        _cruzada(db_session, docente, banco, 3)
    assert exc.value.extras["com_cruzamento"] == 2
    # O teto de cruzamentos é à parte do teto de ativas.
    criar_orientacao_sessao(db_session, docente, sessao_rascunho, "enunciados curtos")


def test_pontual_nao_conta_para_o_teto(db_session, docente, sessao_rascunho):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=1)
    _de_sessao(db_session, docente, sessao_rascunho, 5)
    pontual = _cruzada(db_session, docente, banco, 1, acumular=False)
    assert pontual.estado is EstadoOrientacao.PONTUAL
    assert (pontual.banco_id, pontual.numero_origem) == (banco.id, 1)


def test_variacao_acumulada_vira_ativa(db_session, docente, sessao_rascunho):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=1)
    acumulada = criar_orientacao_questao(
        db_session, docente, banco, 1, None, "use um exemplo de rede", True
    )
    assert acumulada.estado is EstadoOrientacao.ATIVA
    assert acumulada.origem is OrigemOrientacao.QUESTAO


def test_desativar_e_idempotente(db_session, docente, sessao_rascunho):
    [orientacao] = _de_sessao(db_session, docente, sessao_rascunho, 1)
    desativar(db_session, docente, sessao_rascunho, orientacao.id)
    de_novo = desativar(db_session, docente, sessao_rascunho, orientacao.id)
    assert de_novo.estado is EstadoOrientacao.INATIVA
    eventos = db_session.scalars(
        select(RegistroAuditoria).where(
            RegistroAuditoria.tipo_evento
            == TipoEventoAuditoria.ORIENTACAO_DESATIVADA.value
        )
    ).all()
    assert len(eventos) == 1


def test_desativar_pontual_e_recusado(db_session, docente, sessao_rascunho):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=1)
    pontual = _cruzada(db_session, docente, banco, 1, acumular=False)
    with pytest.raises(EstadoOrientacaoInvalidoException):
        desativar(db_session, docente, sessao_rascunho, pontual.id)


def test_desativar_de_outra_sessao_responde_nao_encontrada(
    db_session, docente, sessao_rascunho
):
    from backend.app.schemas.sessao import SessaoCriar
    from backend.app.services.sessao_service import criar_sessao

    outra = criar_sessao(
        db_session,
        docente,
        SessaoCriar(
            disciplina="Redes",
            periodo="2026.2",
            k_alternativas=5,
            p_f=30,
            p_m=40,
            p_d=30,
        ),
    )
    [orientacao] = _de_sessao(db_session, docente, outra, 1)
    with pytest.raises(OrientacaoNaoEncontradaException):
        desativar(db_session, docente, sessao_rascunho, orientacao.id)


def test_vigentes_traz_so_ativas_em_ordem_de_criacao(
    db_session, docente, sessao_rascunho
):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=1)
    primeira, segunda, terceira = _de_sessao(db_session, docente, sessao_rascunho, 3)
    desativar(db_session, docente, sessao_rascunho, segunda.id)
    pontual = _cruzada(db_session, docente, banco, 1, acumular=False)

    assert [o.id for o in vigentes(db_session, sessao_rascunho)] == [
        primeira.id,
        terceira.id,
    ]
    assert [o.id for o in listar(db_session, sessao_rascunho)] == [
        primeira.id,
        segunda.id,
        terceira.id,
        pontual.id,
    ]


def test_registrar_iniciais_nao_faz_commit(db_session, docente, sessao_rascunho):
    registrar_iniciais(db_session, docente, sessao_rascunho, ["a", "b"])
    assert len(vigentes(db_session, sessao_rascunho)) == 2
    db_session.rollback()
    assert vigentes(db_session, sessao_rascunho) == []


def test_eventos_sem_texto_da_orientacao(db_session, docente, sessao_rascunho):
    orientacao = criar_orientacao_sessao(
        db_session, docente, sessao_rascunho, "texto que não pode ir para o log"
    )
    desativar(db_session, docente, sessao_rascunho, orientacao.id)
    registros = db_session.scalars(select(RegistroAuditoria)).all()
    criacao = next(r for r in registros if r.tipo_evento == "orientacao_criada")
    desativacao = next(r for r in registros if r.tipo_evento == "orientacao_desativada")
    assert criacao.entidade_afetada == f"orientacoes_docente:{orientacao.id}"
    assert criacao.payload == {
        "orientacao_id": orientacao.id,
        "origem": "sessao",
        "estado": "ativa",
        "com_cruzamento": False,
    }
    assert desativacao.payload == {"orientacao_id": orientacao.id}
    assert all("não pode ir" not in str(r.payload) for r in registros)


def _sessao_esta_livre(engine, sessao_id: int) -> bool:
    return linha_esta_livre(engine, "sessoes_geracao", sessao_id)


def test_teto_e_contado_com_a_sessao_travada(
    db_session, docente, sessao_rascunho, engine, monkeypatch
):
    """Duas abas acrescentando a 5ª ao mesmo tempo: sem o lock, as duas contam 4
    e as duas gravam."""
    achados: list[bool] = []
    original = orientacao_service._exigir_teto

    def espiao(db, sessao, com_cruzamento):
        achados.append(_sessao_esta_livre(engine, sessao.id))
        return original(db, sessao, com_cruzamento)

    monkeypatch.setattr(orientacao_service, "_exigir_teto", espiao)
    criar_orientacao_sessao(db_session, docente, sessao_rascunho, "x")
    assert achados == [False]
