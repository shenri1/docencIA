from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.exceptions import (
    CredenciaisInvalidasException,
    CredencialJaCadastradaException,
    PerfilInsuficienteException,
    TokenInvalidoException,
)
from backend.app.handlers import registrar_exception_handlers


def _app_de_teste() -> TestClient:
    app = FastAPI()
    registrar_exception_handlers(app)

    @app.get("/levanta/credencial-duplicada")
    def _a():
        raise CredencialJaCadastradaException("123")

    @app.get("/levanta/credenciais-invalidas")
    def _b():
        raise CredenciaisInvalidasException()

    @app.get("/levanta/token-invalido")
    def _c():
        raise TokenInvalidoException()

    @app.get("/levanta/perfil-insuficiente")
    def _d():
        raise PerfilInsuficienteException()

    return TestClient(app, raise_server_exceptions=False)


def test_credencial_duplicada_retorna_409():
    client = _app_de_teste()
    resp = client.get("/levanta/credencial-duplicada")
    assert resp.status_code == 409


def test_credenciais_invalidas_retorna_401():
    client = _app_de_teste()
    resp = client.get("/levanta/credenciais-invalidas")
    assert resp.status_code == 401


def test_token_invalido_retorna_401():
    client = _app_de_teste()
    resp = client.get("/levanta/token-invalido")
    assert resp.status_code == 401


def test_perfil_insuficiente_retorna_403():
    client = _app_de_teste()
    resp = client.get("/levanta/perfil-insuficiente")
    assert resp.status_code == 403
