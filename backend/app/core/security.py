from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from backend.app.core.config import settings
from backend.app.exceptions import TokenInvalidoException

_SENHA_MAX_BYTES = 72


def _senha_bytes_truncados(senha: str) -> bytes:
    """bcrypt (>=5.0) levanta ValueError acima de 72 bytes em vez de truncar
    silenciosamente. Truncamos aqui em vez de deixar a exceção escapar pro
    endpoint — schema (`DocenteCriar.senha`, max_length=72) já barra a
    maioria dos casos, mas `OAuth2PasswordRequestForm` (usado no login) não
    passa pelo schema, então essa é a última linha de defesa contra um 500
    (e contra o oráculo de enumeração de conta que ele criaria no login)."""
    return senha.encode("utf-8")[:_SENHA_MAX_BYTES]


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(_senha_bytes_truncados(senha), bcrypt.gensalt()).decode(
        "utf-8"
    )


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return bcrypt.checkpw(_senha_bytes_truncados(senha), senha_hash.encode("utf-8"))


def criar_access_token(subject: str) -> str:
    expira_em = datetime.now(UTC) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expira_em}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decodificar_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.PyJWTError as exc:
        raise TokenInvalidoException() from exc
