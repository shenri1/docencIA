from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.config import settings
from backend.app.domain import (
    FormatoArquivo,
    OrigemTexto,
    StatusLegibilidade,
    TipoMaterial,
)
from backend.app.models.base import Base

if TYPE_CHECKING:
    from backend.app.models.banco import FonteInterna
    from backend.app.models.identidade import SessaoGeracao


class MaterialReferencia(Base):
    __tablename__ = "materiais_referencia"
    __table_args__ = (
        UniqueConstraint("sessao_id", "hash_sha256", name="material_por_sessao_hash"),
        UniqueConstraint(
            "sessao_id", "identificador_curto", name="material_por_sessao_identificador"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sessao_id: Mapped[int] = mapped_column(ForeignKey("sessoes_geracao.id"), index=True)

    identificador_curto: Mapped[str] = mapped_column(String(16))
    nome_arquivo: Mapped[str] = mapped_column(String(255))
    tipo: Mapped[TipoMaterial] = mapped_column(
        SAEnum(TipoMaterial, name="tipo_material")
    )
    formato: Mapped[FormatoArquivo] = mapped_column(
        SAEnum(FormatoArquivo, name="formato_arquivo")
    )
    status_legibilidade: Mapped[StatusLegibilidade] = mapped_column(
        SAEnum(StatusLegibilidade, name="status_legibilidade"),
        default=StatusLegibilidade.PENDENTE,
    )
    motivo_rejeicao: Mapped[str | None] = mapped_column(String(500))
    contagem_paginas_logicas: Mapped[int | None] = mapped_column(Integer)

    # Chaves lógicas no armazenamento — nunca caminho absoluto, nunca expostas
    # em resposta da API.
    chave_armazenamento: Mapped[str] = mapped_column(String(500))
    chave_texto_extraido: Mapped[str] = mapped_column(String(500))
    hash_sha256: Mapped[str] = mapped_column(String(64))
    tamanho_bytes: Mapped[int] = mapped_column(Integer)
    origem_texto: Mapped[OrigemTexto] = mapped_column(
        SAEnum(OrigemTexto, name="origem_texto")
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sessao: Mapped[SessaoGeracao] = relationship(back_populates="materiais")
    chunks: Mapped[list[ChunkMaterial]] = relationship(
        back_populates="material", cascade="all, delete-orphan"
    )
    fontes_internas: Mapped[list[FonteInterna]] = relationship(
        back_populates="material"
    )


class ChunkMaterial(Base):
    __tablename__ = "chunks_material"
    __table_args__ = (
        Index(
            "ix_chunks_material_embedding_hnsw",
            "vetor_embedding",
            postgresql_using="hnsw",
            postgresql_ops={"vetor_embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materiais_referencia.id"), index=True
    )
    texto: Mapped[str] = mapped_column(Text)
    localizacao: Mapped[str] = mapped_column(String(255))
    vetor_embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim))

    material: Mapped[MaterialReferencia] = relationship(back_populates="chunks")
