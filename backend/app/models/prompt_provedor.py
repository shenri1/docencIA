from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.domain import TipoProvedorLLM
from backend.app.models.base import Base, append_only

if TYPE_CHECKING:
    from backend.app.models.identidade import SessaoGeracao


class PromptMestre(Base):
    __tablename__ = "prompts_mestres"

    id: Mapped[int] = mapped_column(primary_key=True)
    versao: Mapped[str] = mapped_column(String(50), unique=True)
    conteudo: Mapped[str] = mapped_column(Text)
    papel_definido: Mapped[str] = mapped_column(String(255))
    ativo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class ProvedorLLM(Base):
    __tablename__ = "provedores_llm"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100), unique=True)
    # Tag do modelo no provedor (ex.: "qwen3:4b"). endpoint diz onde falar,
    # modelo diz com quem.
    modelo: Mapped[str] = mapped_column(String(100))
    tipo: Mapped[TipoProvedorLLM] = mapped_column(
        SAEnum(TipoProvedorLLM, name="tipo_provedor_llm")
    )
    # NULL = usar settings.llm_base_url. Sem isso, a migração de seed teria
    # que gravar um host, e o host correto difere entre local e Compose.
    endpoint: Mapped[str | None] = mapped_column(String(500))
    preco_input_por_milhao: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    preco_output_por_milhao: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    janela_contexto: Mapped[int] = mapped_column(Integer)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Ordem da cadeia de fallback: menor primeiro.
    prioridade: Mapped[int] = mapped_column(Integer, index=True)
    # Caminho/referência no secrets manager — nunca a chave em si.
    # NULL para provedor local, que não tem chave.
    referencia_chave_secrets: Mapped[str | None] = mapped_column(String(255))

    sessoes: Mapped[list[SessaoGeracao]] = relationship(back_populates="provedor_llm")
    consumos_token: Mapped[list[ConsumoToken]] = relationship(back_populates="provedor")


class ConsumoToken(Base):
    __tablename__ = "consumos_token"

    id: Mapped[int] = mapped_column(primary_key=True)
    sessao_id: Mapped[int] = mapped_column(ForeignKey("sessoes_geracao.id"), index=True)
    provedor_id: Mapped[int] = mapped_column(
        ForeignKey("provedores_llm.id"), index=True
    )
    tokens_input: Mapped[int] = mapped_column(Integer)
    tokens_output: Mapped[int] = mapped_column(Integer)
    custo_estimado: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sessao: Mapped[SessaoGeracao] = relationship(back_populates="consumos_token")
    provedor: Mapped[ProvedorLLM] = relationship(back_populates="consumos_token")


append_only(ConsumoToken)
