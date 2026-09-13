import pytest

from backend.app.exceptions import CredenciaisInvalidasException, CredencialJaCadastradaException
from backend.app.schemas.identidade import DocenteCriar
from backend.app.services.auth_service import autenticar_docente, registrar_docente


def _dados_docente(credencial="prof001"):
    return DocenteCriar(nome="Ana Souza", credencial_institucional=credencial, senha="senhaforte123")


def test_registrar_docente_cria_com_perfil_padrao_e_hash(db_session):
    docente = registrar_docente(db_session, _dados_docente())
    assert docente.id is not None
    assert docente.perfil.value == "docente"
    assert docente.senha_hash != "senhaforte123"


def test_registrar_docente_com_credencial_duplicada_levanta_excecao(db_session):
    registrar_docente(db_session, _dados_docente("dup001"))
    with pytest.raises(CredencialJaCadastradaException):
        registrar_docente(db_session, _dados_docente("dup001"))


def test_autenticar_docente_com_senha_correta_retorna_token(db_session):
    registrar_docente(db_session, _dados_docente("prof002"))
    token = autenticar_docente(db_session, credencial_institucional="prof002", senha="senhaforte123")
    assert isinstance(token, str) and token


def test_autenticar_docente_com_senha_errada_levanta_excecao(db_session):
    registrar_docente(db_session, _dados_docente("prof003"))
    with pytest.raises(CredenciaisInvalidasException):
        autenticar_docente(db_session, credencial_institucional="prof003", senha="senhaerrada")


def test_autenticar_docente_inexistente_levanta_excecao(db_session):
    with pytest.raises(CredenciaisInvalidasException):
        autenticar_docente(db_session, credencial_institucional="nao-existe", senha="qualquer")
