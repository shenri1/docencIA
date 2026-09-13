from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_docente
from backend.app.core.db import get_db
from backend.app.models.identidade import Docente
from backend.app.schemas.identidade import DocenteCriar, DocenteResposta, TokenResponse
from backend.app.services.auth_service import autenticar_docente, registrar_docente

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/registrar", response_model=DocenteResposta, status_code=status.HTTP_201_CREATED)
def registrar(dados: DocenteCriar, db: Session = Depends(get_db)) -> Docente:
    return registrar_docente(db, dados)


@router.post("/login", response_model=TokenResponse)
def login(
    form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> TokenResponse:
    token = autenticar_docente(db, credencial_institucional=form.username, senha=form.password)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=DocenteResposta)
def me(docente: Docente = Depends(get_current_docente)) -> Docente:
    return docente
