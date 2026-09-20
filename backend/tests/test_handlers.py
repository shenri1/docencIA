import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.exceptions import (
    ArquivoCorrompidoException,
    ArquivoMuitoGrandeException,
    ArquivoProtegidoException,
    CredenciaisInvalidasException,
    CredencialJaCadastradaException,
    DomainException,
    FormatoNaoSuportadoException,
    IndiceNaoConfirmadoException,
    IndiceVazioException,
    MaterialDuplicadoException,
    MaterialIlegivelException,
    MaterialNaoEncontradoException,
    MaterialSemTextoException,
    ParametrosInconsistentesException,
    PdfEscaneadoOcrInsuficienteException,
    PdfProtegidoException,
    PerfilInsuficienteException,
    SessaoEstadoInvalidaException,
    SessaoNaoEncontradaException,
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


def test_registrar_com_senha_invalida_nao_ecoa_senha_em_texto_puro(client):
    senha_curta = "abc"
    resp = client.post(
        "/auth/registrar",
        json={
            "nome": "Ana",
            "credencial_institucional": "handler001",
            "senha": senha_curta,
        },
    )
    assert resp.status_code == 422
    assert senha_curta not in resp.text


CASOS = [
    (CredencialJaCadastradaException("abc"), 409, "CREDENCIAL_JA_CADASTRADA"),
    (CredenciaisInvalidasException(), 401, "CREDENCIAIS_INVALIDAS"),
    (TokenInvalidoException(), 401, "TOKEN_INVALIDO"),
    (PerfilInsuficienteException(), 403, "PERFIL_INSUFICIENTE"),
    (ParametrosInconsistentesException(40, 40, 40), 422, "PARAMETROS_INCONSISTENTES"),
    (SessaoNaoEncontradaException(7), 404, "SESSAO_NAO_ENCONTRADA"),
    (
        SessaoEstadoInvalidaException("índice já confirmado"),
        409,
        "SESSAO_ESTADO_INVALIDO",
    ),
    (IndiceVazioException(), 409, "INDICE_VAZIO"),
    (IndiceNaoConfirmadoException(), 409, "INDICE_NAO_CONFIRMADO"),
    (MaterialNaoEncontradoException(3), 404, "MATERIAL_NAO_ENCONTRADO"),
    (MaterialDuplicadoException("P1"), 409, "MATERIAL_DUPLICADO"),
    (ArquivoMuitoGrandeException(30), 413, "ARQUIVO_MUITO_GRANDE"),
    (FormatoNaoSuportadoException("xlsx"), 415, "FORMATO_NAO_SUPORTADO"),
    (PdfProtegidoException("exige senha"), 422, "PDF_PROTEGIDO"),
    (
        PdfEscaneadoOcrInsuficienteException([2, 5], "OCR abaixo do limiar"),
        422,
        "PDF_OCR_INSUFICIENTE",
    ),
    (ArquivoProtegidoException("docx"), 422, "ARQUIVO_PROTEGIDO"),
    (ArquivoCorrompidoException("pptx"), 422, "ARQUIVO_CORROMPIDO"),
    (MaterialSemTextoException("txt"), 422, "MATERIAL_SEM_TEXTO"),
]


@pytest.mark.parametrize("exc,status,codigo", CASOS)
def test_exececoes_declaram_status_e_codigo(exc, status, codigo):
    assert isinstance(exc, DomainException)
    assert exc.status_code == status
    assert exc.codigo == codigo
    corpo = exc.corpo()
    assert corpo["detail"] and corpo["codigo"] == codigo


def test_ilegiveis_carregam_motivo():
    exc = PdfEscaneadoOcrInsuficienteException([2, 5], "OCR abaixo do limiar")
    assert isinstance(exc, MaterialIlegivelException)
    assert exc.corpo()["motivo"] == "OCR abaixo do limiar"
    assert exc.corpo()["paginas_afetadas"] == [2, 5]


def test_handler_generico_responde_qualquer_domain_exception():
    app = FastAPI()
    registrar_exception_handlers(app)

    @app.get("/levanta/duplicado")
    def _a():
        raise MaterialDuplicadoException("P1")

    cliente = TestClient(app, raise_server_exceptions=False)
    resp = cliente.get("/levanta/duplicado")
    assert resp.status_code == 409
    assert resp.json()["codigo"] == "MATERIAL_DUPLICADO"


def test_token_invalido_mantem_header_www_authenticate():
    app = FastAPI()
    registrar_exception_handlers(app)

    @app.get("/levanta/token")
    def _b():
        raise TokenInvalidoException()

    cliente = TestClient(app, raise_server_exceptions=False)
    resp = cliente.get("/levanta/token")
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == "Bearer"
