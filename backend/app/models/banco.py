from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import conv

from backend.app.domain import (
    DecisaoSubstituicao,
    EstadoBanco,
    EstadoQuestao,
    EventoBanco,
    FaixaDificuldade,
    FormatoItem,
    NivelBloom,
    TipoQuestao,
)
from backend.app.models.base import Base, append_only

if TYPE_CHECKING:
    from backend.app.models.identidade import SessaoGeracao
    from backend.app.models.materiais import MaterialReferencia
    from backend.app.models.provas import ExportacaoDocx, ItemProva


class BancoQuestoes(Base):
    __tablename__ = "bancos_questoes"
    __table_args__ = (
        UniqueConstraint("sessao_id", "versao", name="banco_por_sessao_versao"),
        CheckConstraint(
            "n_alvo = n_alvo_objetivas + n_alvo_discursivas",
            # conv(): CheckConstraint aplica a convenção de nomes mesmo com
            # nome explícito — sem isso viraria "ck_bancos_questoes_..." e
            # divergiria do nome literal usado na migração.
            name=conv("n_alvo_soma_tipos"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sessao_id: Mapped[int] = mapped_column(ForeignKey("sessoes_geracao.id"), index=True)
    versao: Mapped[str] = mapped_column(String(50))
    estado: Mapped[EstadoBanco] = mapped_column(
        SAEnum(EstadoBanco, name="estado_banco"), default=EstadoBanco.ABERTO, index=True
    )
    n_alvo: Mapped[int] = mapped_column(Integer)
    # Fixas na criação: mudar a contagem na retomada deslocaria
    # quais números são objetivos e quais são discursivos, e recalcularia as
    # âncoras com outro espaçamento.
    n_alvo_objetivas: Mapped[int] = mapped_column(Integer)
    n_alvo_discursivas: Mapped[int] = mapped_column(Integer)
    # n_atual é o número de questões ATIVA. Excluída, substituída, candidata e
    # descartada não contam.
    n_atual: Mapped[int] = mapped_column(Integer, default=0)
    # contador de revisão, incrementado a cada exclusão, substituição
    # aceita e congelamento. Exibido como "v1.r3".
    revisao: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

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
        # Índices parciais no lugar de UniqueConstraint("banco_id", "numero"):
        # a substituição aceita deixa a original SUBSTITUIDA no mesmo número, e
        # a segunda troca do mesmo número deixa duas. A regra real é "um
        # ocupante (ATIVA ou EXCLUIDA) e uma candidata por número".
        #
        # Os enums nativos guardam o NOME do membro, em maiúsculas.
        Index(
            "questao_por_banco_numero_ocupado",
            "banco_id",
            "numero",
            unique=True,
            postgresql_where=text("estado IN ('ATIVA', 'EXCLUIDA')"),
        ),
        Index(
            "candidata_por_banco_numero",
            "banco_id",
            "numero",
            unique=True,
            postgresql_where=text("estado = 'CANDIDATA'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    banco_id: Mapped[int] = mapped_column(ForeignKey("bancos_questoes.id"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    tipo: Mapped[TipoQuestao] = mapped_column(
        SAEnum(TipoQuestao, name="tipo_questao"),
        index=True,
    )
    # Sem default de propósito: quem diz o formato é o plano do banco.
    # A discursiva grava PROPOSICAO, e o campo não tem leitura para ela.
    formato: Mapped[FormatoItem] = mapped_column(
        SAEnum(FormatoItem, name="formato_item")
    )

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
    aspectos: Mapped[list[AspectoEsperado]] = relationship(
        back_populates="questao",
        cascade="all, delete-orphan",
        order_by="AspectoEsperado.ordem",
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
    """Os 5 campos na objetiva; na discursiva só `objetivo_cognitivo`
    — invalidação de distratores e unicidade não existem sem alternativas.
    Nunca aparece no corpo da questão."""

    __tablename__ = "justificativas_estruturadas"

    id: Mapped[int] = mapped_column(primary_key=True)
    questao_id: Mapped[int] = mapped_column(
        ForeignKey("questoes.id"), unique=True, index=True
    )
    objetivo_cognitivo: Mapped[str] = mapped_column(Text)
    justificativa_correta: Mapped[str | None] = mapped_column(Text)
    invalidacao_distratores: Mapped[list[dict[str, str]] | list[str] | None] = (
        mapped_column(JSONB)
    )
    verificacao_unicidade: Mapped[bool | None] = mapped_column(Boolean)
    texto_verificacao_unicidade: Mapped[str | None] = mapped_column(Text)
    # {"contexto": …} em toda questão nova, mais a estrutura do formato
    # montado (afirmativas; asserção e razão). NULL nas anteriores à etapa.
    estrutura_formato: Mapped[dict | None] = mapped_column(JSONB)

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


class AspectoEsperado(Base):
    """o que uma boa resposta discursiva deveria abordar. Orienta a
    correção do docente; não é gabarito nem rubrica. Cada aspecto aponta a
    fonte que o sustenta — é isso que mantém a discursiva rastreável."""

    __tablename__ = "aspectos_esperados"
    __table_args__ = (
        UniqueConstraint("questao_id", "ordem", name="aspecto_por_questao_ordem"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    questao_id: Mapped[int] = mapped_column(ForeignKey("questoes.id"), index=True)
    ordem: Mapped[int] = mapped_column(Integer)
    # 1, 2 ou 3 na discursiva difícil com itens; NULL sem itens.
    item: Mapped[int | None] = mapped_column(Integer)
    texto: Mapped[str] = mapped_column(Text)
    fonte_interna_id: Mapped[int] = mapped_column(ForeignKey("fontes_internas.id"))

    questao: Mapped[Questao] = relationship(back_populates="aspectos")
    fonte: Mapped[FonteInterna] = relationship()


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
    revisao: Mapped[int] = mapped_column(Integer)
    evento: Mapped[EventoBanco] = mapped_column(
        SAEnum(EventoBanco, name="evento_banco")
    )
    alerta_desvio: Mapped[bool] = mapped_column(Boolean)
    # Aninhado por tipo desde a {"objetiva": {"facil": 6, ...}, ...}
    contagem_por_faixa: Mapped[dict[str, dict[str, int]]] = mapped_column(JSONB)
    # Desvio como TEXTO: Decimal não serializa em JSONB e float não é exato.
    # null quando o tipo foi pedido e não tem nenhuma questão ativa.
    desvio_observado: Mapped[dict[str, dict[str, str | None]]] = mapped_column(JSONB)

    banco: Mapped[BancoQuestoes] = relationship(back_populates="relatorios_impacto")


class RegistroSubstituicao(Base):
    """histórico de trocas, append-only. Sem relationship de
    propósito — duas FKs para `questoes` exigiriam `foreign_keys` em cada uma,
    e nenhuma consulta desta etapa navega por elas."""

    __tablename__ = "registros_substituicao"

    id: Mapped[int] = mapped_column(primary_key=True)
    questao_original_id: Mapped[int] = mapped_column(
        ForeignKey("questoes.id"), index=True
    )
    candidata_id: Mapped[int] = mapped_column(ForeignKey("questoes.id"))
    docente_id: Mapped[int] = mapped_column(ForeignKey("docentes.id"))
    decisao: Mapped[DecisaoSubstituicao] = mapped_column(
        SAEnum(DecisaoSubstituicao, name="decisao_substituicao")
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


append_only(RegistroSubstituicao)
