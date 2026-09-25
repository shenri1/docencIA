from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.domain import (
    EstadoBanco,
    EstadoQuestao,
    FaixaDificuldade,
    NivelBloom,
)
from backend.app.models.base import Base

if TYPE_CHECKING:
    from backend.app.models.identidade import SessaoGeracao
    from backend.app.models.materiais import MaterialReferencia
    from backend.app.models.provas import ExportacaoDocx, ItemProva


class BancoQuestoes(Base):
    __tablename__ = "bancos_questoes"
    __table_args__ = (
        UniqueConstraint("sessao_id", "versao", name="banco_por_sessao_versao"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sessao_id: Mapped[int] = mapped_column(ForeignKey("sessoes_geracao.id"), index=True)
    versao: Mapped[str] = mapped_column(String(50))
    estado: Mapped[EstadoBanco] = mapped_column(
        SAEnum(EstadoBanco, name="estado_banco"), default=EstadoBanco.ABERTO, index=True
    )
    n_alvo: Mapped[int] = mapped_column(Integer)
    n_atual: Mapped[int] = mapped_column(Integer, default=0)

    sessao: Mapped[SessaoGeracao] = relationship(back_populates="bancos")
    questoes: Mapped[list[Questao]] = relationship(
        back_populates="banco", cascade="all, delete-orphan"
    )
    relatorios_impacto: Mapped[list[RelatorioImpacto]] = relationship(
        back_populates="banco", cascade="all, delete-orphan"
    )
    exportacoes: Mapped[list[ExportacaoDocx]] = relationship(back_populates="banco")


class Questao(Base):
    __tablename__ = "questoes"
    __table_args__ = (
        UniqueConstraint("banco_id", "numero", name="questao_por_banco_numero"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    banco_id: Mapped[int] = mapped_column(ForeignKey("bancos_questoes.id"), index=True)
    numero: Mapped[int] = mapped_column(Integer)

    enunciado: Mapped[str] = mapped_column(Text)
    nivel_bloom: Mapped[NivelBloom] = mapped_column(
        SAEnum(NivelBloom, name="nivel_bloom")
    )
    faixa_dificuldade: Mapped[FaixaDificuldade] = mapped_column(
        SAEnum(FaixaDificuldade, name="faixa_dificuldade")
    )
    tema: Mapped[str | None] = mapped_column(String(255))
    subtema: Mapped[str | None] = mapped_column(String(255))
    estado: Mapped[EstadoQuestao] = mapped_column(
        SAEnum(EstadoQuestao, name="estado_questao"),
        default=EstadoQuestao.ATIVA,
        index=True,
    )

    banco: Mapped[BancoQuestoes] = relationship(back_populates="questoes")
    alternativas: Mapped[list[Alternativa]] = relationship(
        back_populates="questao", cascade="all, delete-orphan"
    )
    fontes_internas: Mapped[list[FonteInterna]] = relationship(
        back_populates="questao", cascade="all, delete-orphan"
    )
    justificativa: Mapped[JustificativaEstruturada | None] = relationship(
        back_populates="questao", cascade="all, delete-orphan"
    )
    revisao: Mapped[RevisaoQuestao | None] = relationship(
        back_populates="questao", cascade="all, delete-orphan"
    )
    exclusoes: Mapped[list[RegistroExclusao]] = relationship(back_populates="questao")
    itens_prova: Mapped[list[ItemProva]] = relationship(back_populates="questao")


class Alternativa(Base):
    __tablename__ = "alternativas"
    __table_args__ = (
        UniqueConstraint("questao_id", "letra", name="alternativa_por_questao_letra"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    questao_id: Mapped[int] = mapped_column(ForeignKey("questoes.id"), index=True)
    letra: Mapped[str] = mapped_column(String(2))
    texto: Mapped[str] = mapped_column(Text)
    correta: Mapped[bool] = mapped_column(Boolean, default=False)
    # Gêmeo malvado: distrator que espelha a correta.
    e_gemeo_malvado: Mapped[bool] = mapped_column(Boolean, default=False)

    questao: Mapped[Questao] = relationship(back_populates="alternativas")


class FonteInterna(Base):
    __tablename__ = "fontes_internas"

    id: Mapped[int] = mapped_column(primary_key=True)
    questao_id: Mapped[int] = mapped_column(ForeignKey("questoes.id"), index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materiais_referencia.id"))
    localizacao: Mapped[str] = mapped_column(String(255))
    trecho_base: Mapped[str] = mapped_column(Text)

    questao: Mapped[Questao] = relationship(back_populates="fontes_internas")
    material: Mapped[MaterialReferencia] = relationship(
        back_populates="fontes_internas"
    )


class JustificativaEstruturada(Base):
    """Os 5 campos. Nunca aparece no corpo da questão."""

    __tablename__ = "justificativas_estruturadas"

    id: Mapped[int] = mapped_column(primary_key=True)
    questao_id: Mapped[int] = mapped_column(
        ForeignKey("questoes.id"), unique=True, index=True
    )
    objetivo_cognitivo: Mapped[str] = mapped_column(Text)
    justificativa_correta: Mapped[str] = mapped_column(Text)
    invalidacao_distratores: Mapped[list[str]] = mapped_column(JSONB)
    verificacao_unicidade: Mapped[bool] = mapped_column(Boolean)
    texto_verificacao_unicidade: Mapped[str] = mapped_column(Text)

    questao: Mapped[Questao] = relationship(back_populates="justificativa")


class RevisaoQuestao(Base):
    """o rascunho e as violações de forma antes e depois da revisão.
    Tabela própria pelo mesmo motivo da JustificativaEstruturada: nada daqui
    pode vazar no corpo da questão. "Aprovada na autoauditoria" não é coluna:
    é violacoes_final vazio, e coluna derivada seria mais um lugar para
    divergir."""

    __tablename__ = "revisoes_questao"

    id: Mapped[int] = mapped_column(primary_key=True)
    questao_id: Mapped[int] = mapped_column(
        ForeignKey("questoes.id"), unique=True, index=True
    )
    rascunho: Mapped[dict] = mapped_column(JSONB)
    violacoes_rascunho: Mapped[list[dict]] = mapped_column(JSONB)
    violacoes_final: Mapped[list[dict]] = mapped_column(JSONB)
    modelo_geracao: Mapped[str] = mapped_column(String(100))
    modelo_revisao: Mapped[str] = mapped_column(String(100))

    questao: Mapped[Questao] = relationship(back_populates="revisao")


class RegistroExclusao(Base):
    __tablename__ = "registros_exclusao"

    id: Mapped[int] = mapped_column(primary_key=True)
    questao_id: Mapped[int] = mapped_column(ForeignKey("questoes.id"), index=True)
    docente_id: Mapped[int] = mapped_column(ForeignKey("docentes.id"))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    questao: Mapped[Questao] = relationship(back_populates="exclusoes")


class RelatorioImpacto(Base):
    __tablename__ = "relatorios_impacto"

    id: Mapped[int] = mapped_column(primary_key=True)
    banco_id: Mapped[int] = mapped_column(ForeignKey("bancos_questoes.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    n_final: Mapped[int] = mapped_column(Integer)
    contagem_por_faixa: Mapped[dict[str, int]] = mapped_column(JSONB)
    desvio_observado: Mapped[dict[str, Decimal]] = mapped_column(JSONB)

    banco: Mapped[BancoQuestoes] = relationship(back_populates="relatorios_impacto")
