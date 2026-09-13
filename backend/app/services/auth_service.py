"""Autenticação de docentes — não orquestra LLM (núcleo determinístico
auxiliar, infraestrutura de identidade)."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.security import criar_access_token, hash_senha, verificar_senha
from backend.app.domain import PerfilDocente
from backend.app.exceptions import (
    CredenciaisInvalidasException,
    CredencialJaCadastradaException,
)
from backend.app.models.identidade import Docente
from backend.app.schemas.identidade import DocenteCriar

# Hash de referência usado quando a credencial não existe, pra que
# autenticar_docente sempre pague o custo de um bcrypt.checkpw — evita que o
# tempo de resposta vaze se a conta existe (timing oracle). Calculado uma
# única vez na importação do módulo, não a cada requisição.
_HASH_DUMMY = hash_senha("dummy-password-for-timing-safety")


def registrar_docente(db: Session, dados: DocenteCriar) -> Docente:
    existente = (
        db.query(Docente)
        .filter_by(credencial_institucional=dados.credencial_institucional)
        .first()
    )
    if existente is not None:
        raise CredencialJaCadastradaException(dados.credencial_institucional)

    docente = Docente(
        nome=dados.nome,
        credencial_institucional=dados.credencial_institucional,
        senha_hash=hash_senha(dados.senha),
        perfil=PerfilDocente.DOCENTE,
    )
    db.add(docente)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise CredencialJaCadastradaException(dados.credencial_institucional) from None
    db.refresh(docente)
    return docente


def autenticar_docente(db: Session, credencial_institucional: str, senha: str) -> str:
    docente = (
        db.query(Docente)
        .filter_by(credencial_institucional=credencial_institucional)
        .first()
    )
    senha_hash_referencia = docente.senha_hash if docente is not None else _HASH_DUMMY
    senha_confere = verificar_senha(senha, senha_hash_referencia)
    if docente is None or not senha_confere:
        raise CredenciaisInvalidasException()
    return criar_access_token(subject=str(docente.id))
