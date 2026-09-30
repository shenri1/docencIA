from __future__ import annotations

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from backend.app.core.config import settings
from backend.app.exceptions import TokenInvalidoException

_SENHA_MAX_BYTES = 72


def _senha_bytes_truncados(senha: str) -> bytes:
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
    except jwt.ExpiredSignatureError as exc:
        # O PyJWT confere a assinatura antes da expiração: expirado é token
        # legítimo que acabou, não suspeito.
        raise TokenInvalidoException(motivo="expirado") from exc
    except jwt.PyJWTError as exc:
        raise TokenInvalidoException(motivo="assinatura_invalida") from exc
