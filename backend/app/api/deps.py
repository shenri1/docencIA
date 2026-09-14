from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.core.security import decodificar_token
from backend.app.domain import PerfilDocente
from backend.app.exceptions import PerfilInsuficienteException, TokenInvalidoException
from backend.app.models.identidade import Docente

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

_ORDEM_PERFIL = {
    PerfilDocente.DOCENTE: 0,
    PerfilDocente.COORDENADOR: 1,
    PerfilDocente.ADMINISTRADOR: 2,
}


def get_current_docente(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Docente:
    payload = decodificar_token(token)
    try:
        docente_id = int(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise TokenInvalidoException() from exc
    docente = db.get(Docente, docente_id)
    if docente is None:
        raise TokenInvalidoException()
    return docente


def require_perfil(minimo: PerfilDocente):
    def _checar(docente: Docente = Depends(get_current_docente)) -> Docente:
        if _ORDEM_PERFIL[docente.perfil] < _ORDEM_PERFIL[minimo]:
            raise PerfilInsuficienteException()
        return docente

    return _checar
