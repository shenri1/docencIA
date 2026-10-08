import threading
from collections.abc import Callable, Generator

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.db import get_db
from backend.app.domain import PerfilDocente
from backend.app.exceptions import ServidorOcupadoException
from backend.app.models.identidade import Docente
from backend.app.services.auth_service import docente_do_token, exigir_perfil
from backend.app.services.provedor.provedor_service import (
    ProvedorLLMService,
    criar_provedor_service,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

_vagas_llm = threading.BoundedSemaphore(settings.llm_max_concorrentes)
_RETRY_AFTER_LLM_S = 30


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


def get_provedor(db: Session = Depends(get_db)) -> Generator[ProvedorLLMService]:
    """Adaptador FastAPI para `criar_provedor_service`, que fica sem `Depends`
    de propósito. É também o ponto de sobrescrita nos testes de API.

    Todo endpoint que chama LLM depende disto, então é aqui que a vaga é
    tomada — sem bloquear: sem vaga, 503 na hora — e devolvida ao fim da
    requisição, inclusive quando ela falha. A dependência de autenticação vem
    antes nas assinaturas, então requisição sem token nunca toma vaga."""
    if not _vagas_llm.acquire(blocking=False):
        raise ServidorOcupadoException(_RETRY_AFTER_LLM_S)
    try:
        yield criar_provedor_service(db)
    finally:
        _vagas_llm.release()


def get_provedor_sob_demanda(
    db: Session = Depends(get_db),
) -> Generator[Callable[[], ProvedorLLMService]]:
    """Como `get_provedor`, mas a vaga só é tomada quando o service chama o
    resultado. Para rotas em que só alguns ramos chamam LLM (`/comando`): os
    determinísticos não podem tomar 503 por causa de geração alheia."""
    tomou = False
    criado: ProvedorLLMService | None = None

    def obter() -> ProvedorLLMService:
        # Uma vaga por requisição: chamar de novo devolve o mesmo service, em
        # vez de tomar outra vaga que o `finally` não devolveria.
        nonlocal tomou, criado
        if criado is None:
            if not tomou:
                if not _vagas_llm.acquire(blocking=False):
                    raise ServidorOcupadoException(_RETRY_AFTER_LLM_S)
                tomou = True
            criado = criar_provedor_service(db)
        return criado

    try:
        yield obter
    finally:
        if tomou:
            _vagas_llm.release()
