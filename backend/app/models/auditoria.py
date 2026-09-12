from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, append_only


class RegistroAuditoria(Base):
    __tablename__ = "registros_auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo_evento: Mapped[str] = mapped_column(String(100), index=True)
    entidade_afetada: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSONB)
    ator: Mapped[str | None] = mapped_column(String(255))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


append_only(RegistroAuditoria)
