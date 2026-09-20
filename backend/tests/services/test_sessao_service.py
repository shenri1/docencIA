import pytest

from backend.app.domain import EstadoSessao
from backend.app.exceptions import (
    IndiceNaoConfirmadoException,
    ParametrosInconsistentesException,
    SessaoNaoEncontradaException,
)
from backend.app.schemas.identidade import DocenteCriar
from backend.app.schemas.sessao import SessaoCriar
from backend.app.services.auth_service import registrar_docente
from backend.app.services.sessao_service import (
    criar_sessao,
    exigir_indice_confirmado,
    listar_sessoes,
    obter_sessao,
)
from backend.app.services.validacao_parametros_service import validar_distribuicao


def _dados(p_f=30, p_m=40, p_d=30) -> SessaoCriar:
    return SessaoCriar(
        disciplina="Cálculo I",
        periodo="2026.2",
        k_alternativas=5,
        p_f=p_f,
        p_m=p_m,
        p_d=p_d,
    )


def test_validar_distribuicao_aceita_soma_100():
    validar_distribuicao(30, 40, 30)


def test_validar_distribuicao_rejeita_soma_diferente_de_100():
    with pytest.raises(ParametrosInconsistentesException):
        validar_distribuicao(30, 40, 40)


def test_criar_sessao_nasce_em_rascunho_e_pertence_ao_docente(db_session, docente):
    sessao = criar_sessao(db_session, docente, _dados())
    assert sessao.id is not None
    assert sessao.docente_id == docente.id
    assert sessao.estado == EstadoSessao.RASCUNHO


def test_criar_sessao_com_distribuicao_invalida_nao_persiste(db_session, docente):
    with pytest.raises(ParametrosInconsistentesException):
        criar_sessao(db_session, docente, _dados(p_d=40))
    assert listar_sessoes(db_session, docente) == []


def test_listar_sessoes_so_traz_as_do_proprio_docente(db_session, docente):
    criar_sessao(db_session, docente, _dados())
    outro = registrar_docente(
        db_session,
        DocenteCriar(
            nome="Bruno", credencial_institucional="outro-prof", senha="senhaforte123"
        ),
    )
    assert listar_sessoes(db_session, outro) == []
    assert len(listar_sessoes(db_session, docente)) == 1


def test_obter_sessao_de_outro_docente_levanta_nao_encontrada(db_session, docente):
    sessao = criar_sessao(db_session, docente, _dados())
    outro = registrar_docente(
        db_session,
        DocenteCriar(
            nome="Bruno", credencial_institucional="outro-prof", senha="senhaforte123"
        ),
    )
    with pytest.raises(SessaoNaoEncontradaException):
        obter_sessao(db_session, outro, sessao.id)


def test_exigir_indice_confirmado_bloqueia_sessao_em_rascunho(db_session, docente):
    sessao = criar_sessao(db_session, docente, _dados())
    with pytest.raises(IndiceNaoConfirmadoException):
        exigir_indice_confirmado(sessao)


def test_exigir_indice_confirmado_passa_apos_confirmacao(db_session, docente):
    sessao = criar_sessao(db_session, docente, _dados())
    sessao.estado = EstadoSessao.MATERIAIS_CONFIRMADOS
    exigir_indice_confirmado(sessao)
