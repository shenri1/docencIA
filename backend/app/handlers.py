from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.exceptions import (
    CredenciaisInvalidasException,
    CredencialJaCadastradaException,
    PerfilInsuficienteException,
    TokenInvalidoException,
)


def registrar_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validacao_invalida(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        erros = jsonable_encoder(exc.errors())
        for erro in erros:
            if "senha" in erro.get("loc", ()):
                erro["input"] = "[redacted]"
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": erros},
        )

    @app.exception_handler(CredencialJaCadastradaException)
    async def _credencial_duplicada(
        _request: Request, exc: CredencialJaCadastradaException
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(CredenciaisInvalidasException)
    async def _credenciais_invalidas(
        _request: Request, exc: CredenciaisInvalidasException
    ) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    @app.exception_handler(TokenInvalidoException)
    async def _token_invalido(
        _request: Request, exc: TokenInvalidoException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"detail": str(exc)},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(PerfilInsuficienteException)
    async def _perfil_insuficiente(
        _request: Request, exc: PerfilInsuficienteException
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})
