from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.domain import EstadoSessao, PerfilDocente
from backend.app.models.base import Base

if TYPE_CHECKING:
    from backend.app.models.banco import BancoQuestoes
    from backend.app.models.materiais import MaterialReferencia
    from backend.app.models.prompt_provedor import ConsumoToken, ProvedorLLM
    from backend.app.models.provas import Prova


class Docente(Base):
    __tablename__ = "docentes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(255))
    credencial_institucional: Mapped[str] = mapped_column(String(255), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    perfil: Mapped[PerfilDocente] = mapped_column(
        SAEnum(PerfilDocente, name="perfil_docente")
    )

    sessoes: Mapped[list[SessaoGeracao]] = relationship(back_populates="docente")


class SessaoGeracao(Base):
    __tablename__ = "sessoes_geracao"
    __table_args__ = (
        CheckConstraint("p_f + p_m + p_d = 100", name="distribuicao_soma_100"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    docente_id: Mapped[int] = mapped_column(ForeignKey("docentes.id"), index=True)

    disciplina: Mapped[str] = mapped_column(String(255))
    periodo: Mapped[str] = mapped_column(String(50))
    tema_escopo: Mapped[str | None] = mapped_column(String(500))
    # Flag que ativa o campo de raciocínio clínico por questão.
    area_do_conhecimento: Mapped[str | None] = mapped_column(String(255))

    k_alternativas: Mapped[int] = mapped_column(Integer)
    p_f: Mapped[int] = mapped_column(Integer)
    p_m: Mapped[int] = mapped_column(Integer)
    p_d: Mapped[int] = mapped_column(Integer)

    provedor_llm_id: Mapped[int | None] = mapped_column(
        ForeignKey("provedores_llm.id"), index=True
    )
    estado: Mapped[EstadoSessao] = mapped_column(
        SAEnum(EstadoSessao, name="estado_sessao"), default=EstadoSessao.RASCUNHO
    )

    docente: Mapped[Docente] = relationship(back_populates="sessoes")
    provedor_llm: Mapped[ProvedorLLM | None] = relationship(back_populates="sessoes")
    materiais: Mapped[list[MaterialReferencia]] = relationship(
        back_populates="sessao", cascade="all, delete-orphan"
    )
    bancos: Mapped[list[BancoQuestoes]] = relationship(
        back_populates="sessao", cascade="all, delete-orphan"
    )
    provas: Mapped[list[Prova]] = relationship(
        back_populates="sessao", cascade="all, delete-orphan"
    )
    consumos_token: Mapped[list[ConsumoToken]] = relationship(back_populates="sessao")
