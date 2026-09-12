from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.domain import EstadoProva, TipoExportacao, TipoGabarito
from backend.app.models.base import Base

if TYPE_CHECKING:
    from backend.app.models.banco import BancoQuestoes, Questao
    from backend.app.models.identidade import SessaoGeracao


class Prova(Base):
    __tablename__ = "provas"
    __table_args__ = (
        UniqueConstraint("sessao_id", "versao", name="prova_por_sessao_versao"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sessao_id: Mapped[int] = mapped_column(ForeignKey("sessoes_geracao.id"), index=True)
    versao: Mapped[str] = mapped_column(String(50))
    n_questoes: Mapped[int] = mapped_column(Integer)
    estado: Mapped[EstadoProva] = mapped_column(
        SAEnum(EstadoProva, name="estado_prova"), default=EstadoProva.RASCUNHO
    )

    sessao: Mapped[SessaoGeracao] = relationship(back_populates="provas")
    itens: Mapped[list[ItemProva]] = relationship(
        back_populates="prova", cascade="all, delete-orphan"
    )
    gabaritos: Mapped[list[Gabarito]] = relationship(
        back_populates="prova", cascade="all, delete-orphan"
    )
    exportacoes: Mapped[list[ExportacaoDocx]] = relationship(back_populates="prova")


class ItemProva(Base):
    __tablename__ = "itens_prova"
    __table_args__ = (
        UniqueConstraint("prova_id", "posicao", name="item_por_prova_posicao"),
        UniqueConstraint("prova_id", "questao_id", name="item_por_prova_questao"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    prova_id: Mapped[int] = mapped_column(ForeignKey("provas.id"), index=True)
    questao_id: Mapped[int] = mapped_column(ForeignKey("questoes.id"), index=True)
    posicao: Mapped[int] = mapped_column(Integer)
    letra_atribuida: Mapped[str] = mapped_column(String(2))

    prova: Mapped[Prova] = relationship(back_populates="itens")
    questao: Mapped[Questao] = relationship(back_populates="itens_prova")


class Gabarito(Base):
    __tablename__ = "gabaritos"

    id: Mapped[int] = mapped_column(primary_key=True)
    prova_id: Mapped[int] = mapped_column(ForeignKey("provas.id"), index=True)
    tipo: Mapped[TipoGabarito] = mapped_column(
        SAEnum(TipoGabarito, name="tipo_gabarito")
    )
    versao: Mapped[str] = mapped_column(String(50))

    prova: Mapped[Prova] = relationship(back_populates="gabaritos")


class ExportacaoDocx(Base):
    __tablename__ = "exportacoes_docx"
    __table_args__ = (
        CheckConstraint(
            "(prova_id IS NULL) <> (banco_id IS NULL)",
            name="exportacao_referencia_unica",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    prova_id: Mapped[int | None] = mapped_column(ForeignKey("provas.id"), index=True)
    banco_id: Mapped[int | None] = mapped_column(
        ForeignKey("bancos_questoes.id"), index=True
    )
    tipo: Mapped[TipoExportacao] = mapped_column(
        SAEnum(TipoExportacao, name="tipo_exportacao")
    )
    caminho_arquivo: Mapped[str] = mapped_column(String(500))
    # Hash do conteúdo renderizado: base da checagem de consistência.
    hash_conteudo: Mapped[str] = mapped_column(String(128))

    prova: Mapped[Prova | None] = relationship(back_populates="exportacoes")
    banco: Mapped[BancoQuestoes | None] = relationship(back_populates="exportacoes")
