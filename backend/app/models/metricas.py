"""Métricas de geração: uma linha por tentativa de produzir um número.

Tabela de análise, lida por SQL. Sem `relationship` em `BancoQuestoes` nem em
`Questao`: o CASCADE e o SET NULL são do banco, e o ORM não deve tentar anular
nada. Strings em vez de enums nativos: um membro novo de `FormatoItem` não pode
pedir migração aqui.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class MetricaGeracao(Base):
    __tablename__ = "metricas_geracao"

    id: Mapped[int] = mapped_column(primary_key=True)
    banco_id: Mapped[int] = mapped_column(
        ForeignKey("bancos_questoes.id", ondelete="CASCADE"), index=True
    )
    numero: Mapped[int] = mapped_column(Integer)
    questao_id: Mapped[int | None] = mapped_column(
        ForeignKey("questoes.id", ondelete="SET NULL")
    )
    origem: Mapped[str] = mapped_column(String(20))
    desfecho: Mapped[str] = mapped_column(String(30))
    motivo: Mapped[str | None] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(30))
    faixa: Mapped[str] = mapped_column(String(30))
    formato_planejado: Mapped[str] = mapped_column(String(30))
    formato_final: Mapped[str | None] = mapped_column(String(30))
    motivo_recuo: Mapped[str | None] = mapped_column(String(30))
    modelo_geracao: Mapped[str | None] = mapped_column(String(100))
    modelo_revisao: Mapped[str | None] = mapped_column(String(100))
    iniciada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tempos_ms: Mapped[dict] = mapped_column(JSONB)
    tokens: Mapped[list] = mapped_column(JSONB)
    rag: Mapped[list] = mapped_column(JSONB)
    sustentacao: Mapped[list | None] = mapped_column(JSONB)
    aderencia: Mapped[dict | None] = mapped_column(JSONB)
