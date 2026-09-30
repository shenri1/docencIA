from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.domain import PerfilDocente
from backend.app.models.identidade import Docente
from backend.app.services.auth_service import docente_do_token, exigir_perfil
from backend.app.services.provedor.provedor_service import (
    ProvedorLLMService,
    criar_provedor_service,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_docente(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Docente:
    return docente_do_token(db, token)


def require_perfil(minimo: PerfilDocente):
    def _checar(
        docente: Docente = Depends(get_current_docente),
        db: Session = Depends(get_db),
    ) -> Docente:
        exigir_perfil(db, docente, minimo)
        return docente

    return _checar


def get_provedor(db: Session = Depends(get_db)) -> ProvedorLLMService:
    """Adaptador FastAPI para `criar_provedor_service`, que fica sem `Depends`
    de propósito. É também o ponto de sobrescrita nos testes de API."""
    return criar_provedor_service(db)
