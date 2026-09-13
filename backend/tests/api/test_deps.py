import pytest

from backend.app.api.deps import _ORDEM_PERFIL, get_current_docente, require_perfil
from backend.app.core.security import criar_access_token
from backend.app.domain import PerfilDocente
from backend.app.exceptions import PerfilInsuficienteException, TokenInvalidoException
from backend.app.schemas.identidade import DocenteCriar
from backend.app.services.auth_service import registrar_docente


def test_get_current_docente_com_token_valido_retorna_docente(db_session):
    docente = registrar_docente(
        db_session,
        DocenteCriar(
            nome="Ana", credencial_institucional="dep001", senha="senhaforte123"
        ),
    )
    token = criar_access_token(subject=str(docente.id))
    resultado = get_current_docente(token=token, db=db_session)
    assert resultado.id == docente.id


def test_get_current_docente_com_token_invalido_levanta_excecao(db_session):
    with pytest.raises(TokenInvalidoException):
        get_current_docente(token="lixo.invalido.aqui", db=db_session)


def test_get_current_docente_com_docente_inexistente_levanta_excecao(db_session):
    token = criar_access_token(subject="99999")
    with pytest.raises(TokenInvalidoException):
        get_current_docente(token=token, db=db_session)


def test_require_perfil_permite_perfil_igual_ao_minimo(db_session):
    docente = registrar_docente(
        db_session,
        DocenteCriar(
            nome="Ana", credencial_institucional="dep002", senha="senhaforte123"
        ),
    )
    checar = require_perfil(PerfilDocente.DOCENTE)
    assert checar(docente=docente) is docente


def test_require_perfil_nega_perfil_abaixo_do_minimo(db_session):
    docente = registrar_docente(
        db_session,
        DocenteCriar(
            nome="Ana", credencial_institucional="dep003", senha="senhaforte123"
        ),
    )
    checar = require_perfil(PerfilDocente.ADMINISTRADOR)
    with pytest.raises(PerfilInsuficienteException):
        checar(docente=docente)


def test_ordem_perfil_cobre_todos_os_perfis_do_enum():
    assert set(_ORDEM_PERFIL) == set(PerfilDocente)
