from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.exceptions import DomainException

# Redige por trecho do nome do campo, não por nome exato: o formulário de login
# usa "password", o cadastro "senha", e um campo novo de credencial não deve
# depender de alguém lembrar de editar esta lista.
_TRECHOS_SENSIVEIS = ("senha", "password", "secret", "token")


def _campo_sensivel(loc: list) -> bool:
    return any(
        isinstance(parte, str) and any(t in parte.lower() for t in _TRECHOS_SENSIVEIS)
        for parte in loc
    )


def registrar_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validacao_invalida(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        erros = jsonable_encoder(exc.errors())
        for erro in erros:
            if _campo_sensivel(erro.get("loc", ())):
                erro["input"] = "[redacted]"
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": erros},
        )

    @app.exception_handler(DomainException)
    async def _dominio(_request: Request, exc: DomainException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content=exc.corpo(), headers=exc.headers
        )
