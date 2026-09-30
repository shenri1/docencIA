"""Log de auditoria e pseudônimo — Núcleo Determinístico.

`registrar_evento` não faz commit: o evento entra na transação da mudança que o
motivou, e uma mudança desfeita leva o evento junto. Quem registra uma recusa
(falha de provedor, login falho, token suspeito, acesso negado) faz o commit
antes de levantar — senão o rollback do erro apagaria o registro.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.domain import TipoEventoAuditoria
from backend.app.models.auditoria import RegistroAuditoria


def _hmac(valor: str) -> str:
    return hmac.new(
        settings.pseudonimo_key.encode(), valor.encode(), hashlib.sha256
    ).hexdigest()


def pseudonimo(docente_id: int) -> str:
    """Do id, não da credencial: a credencial pode mudar de formato."""
    return _hmac(f"docente:{docente_id}")


def pseudonimo_credencial(credencial: str) -> str:
    """Para login com credencial inexistente, onde não há id. O prefixo separa
    os domínios: a credencial "17" não colide com o docente de id 17."""
    return _hmac(f"credencial:{credencial}")


def registrar_evento(
    db: Session,
    tipo: TipoEventoAuditoria,
    entidade: str,
    docente_id: int | None,
    payload: dict,
) -> RegistroAuditoria:
    registro = RegistroAuditoria(
        tipo_evento=tipo.value,
        entidade_afetada=entidade,
        ator=pseudonimo(docente_id) if docente_id is not None else None,
        payload=payload,
    )
    db.add(registro)
    return registro


def listar_eventos(
    db: Session,
    tipo: TipoEventoAuditoria | None,
    desde: datetime | None,
    ate: datetime | None,
    limite: int,
    deslocamento: int,
) -> list[RegistroAuditoria]:
    """`desde` inclusivo, `ate` exclusivo. Mais recente primeiro."""
    consulta = select(RegistroAuditoria)
    if tipo is not None:
        consulta = consulta.where(RegistroAuditoria.tipo_evento == tipo.value)
    if desde is not None:
        consulta = consulta.where(RegistroAuditoria.timestamp >= desde)
    if ate is not None:
        consulta = consulta.where(RegistroAuditoria.timestamp < ate)
    return list(
        db.scalars(
            consulta.order_by(RegistroAuditoria.id.desc())
            .limit(limite)
            .offset(deslocamento)
        )
    )
