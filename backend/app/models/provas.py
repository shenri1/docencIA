from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.domain import EstadoProva, TipoExportacao, TipoGabarito
from backend.app.models.base import Base, append_only

if TYPE_CHECKING:
    from backend.app.models.banco import BancoQuestoes, Questao
    from backend.app.models.identidade import SessaoGeracao


class Prova(Base):
    __tablename__ = "provas"
    __table_args__ = (
        UniqueConstraint("sessao_id", "versao", name="prova_por_sessao_versao"),
        CheckConstraint(
            "n_questoes = n_objetivas + n_discursivas",
            name="n_questoes_soma_tipos",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sessao_id: Mapped[int] = mapped_column(ForeignKey("sessoes_geracao.id"), index=True)
    versao: Mapped[str] = mapped_column(String(50))
    n_questoes: Mapped[int] = mapped_column(Integer)
    # De qual banco a prova foi montada, e em que revisão dele. 
    # prometeu que "inconsistência de estado" viraria comparação de inteiros:
    # é esta coluna contra BancoQuestoes.revisao. `sessao_id` continua sendo o
    # que a UniqueConstraint usa, e é preenchido de banco.sessao_id.
    banco_id: Mapped[int] = mapped_column(ForeignKey("bancos_questoes.id"), index=True)
    revisao_banco: Mapped[int] = mapped_column(Integer)
    n_objetivas: Mapped[int] = mapped_column(Integer)
    n_discursivas: Mapped[int] = mapped_column(Integer)
    estado: Mapped[EstadoProva] = mapped_column(
        SAEnum(EstadoProva, name="estado_prova"), default=EstadoProva.RASCUNHO
    )

    sessao: Mapped[SessaoGeracao] = relationship(back_populates="provas")
    banco: Mapped[BancoQuestoes] = relationship()
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
    # NULL na discursiva: é sobre alternativas.
    letra_atribuida: Mapped[str | None] = mapped_column(String(2))
    # Letras ORIGINAIS na ordem em que aparecem na prova. ["C","A","E","B","D"]
    # significa que a alternativa C original é exibida como A. 
    # renderiza lendo isto e não decide nada. NULL na discursiva.
    ordem_alternativas: Mapped[list[str] | None] = mapped_column(JSONB)

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
    """O arquivo SAI do sistema: depois que a revisão do banco muda, o
    estado antigo não pode mais ser re-renderizado, e só este registro prova o
    que foi entregue e de qual revisão. Append-only."""

    __tablename__ = "exportacoes_docx"
    __table_args__ = (
        CheckConstraint(
            "(prova_id IS NULL) <> (banco_id IS NULL)",
            name="exportacao_referencia_unica",
        ),
        # Exportar de novo na mesma revisão devolve o registro existente: o
        # arquivo é reproduzível, e uma segunda linha só duplicaria histórico.
        UniqueConstraint(
            "banco_id",
            "revisao_banco",
            "tipo",
            name="exportacao_por_banco_revisao_tipo",
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
    # Chave LÓGICA do armazenamento, apesar do nome herdado
    # da migração inicial. Nunca aparece em resposta HTTP.
    caminho_arquivo: Mapped[str] = mapped_column(String(500))
    # Hash do conteúdo renderizado: base da checagem de consistência.
    hash_conteudo: Mapped[str] = mapped_column(String(128))
    revisao_banco: Mapped[int] = mapped_column(Integer)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    prova: Mapped[Prova | None] = relationship(back_populates="exportacoes")
    banco: Mapped[BancoQuestoes | None] = relationship(back_populates="exportacoes")


append_only(ExportacaoDocx)
