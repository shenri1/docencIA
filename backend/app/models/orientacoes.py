"""Orientações do docente.

Append-only com um único UPDATE, ATIVA → INATIVA: editar é desativar e criar
outra. É o que garante que a orientação que gerou cada questão nunca se perde,
como `RegistroExclusao` e `RegistroSubstituicao`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from backend.app.domain import EstadoOrientacao, OrigemOrientacao
from backend.app.models.base import Base

# Gravada com a questão, na mesma transação. Sem model: nenhuma consulta precisa
# dela além da relação `Questao.orientacoes`.
questoes_orientacoes = Table(
    "questoes_orientacoes",
    Base.metadata,
    Column("questao_id", ForeignKey("questoes.id"), primary_key=True),
    Column("orientacao_id", ForeignKey("orientacoes_docente.id"), primary_key=True),
)


class OrientacaoDocente(Base):
    __tablename__ = "orientacoes_docente"
    __table_args__ = (
        # conv(): nome literal, igual ao da migração (ver BancoQuestoes).
        CheckConstraint(
            "o_que_mudar IS NOT NULL OR cruzar_com IS NOT NULL",
            name=conv("orientacao_tem_texto"),
        ),
        # Os enums nativos guardam o NOME do membro, em maiúsculas.
        CheckConstraint(
            "(origem = 'SESSAO' AND banco_id IS NULL AND numero_origem IS NULL "
            "AND cruzar_com IS NULL) OR (origem = 'QUESTAO' AND banco_id IS NOT "
            "NULL AND numero_origem IS NOT NULL)",
            name=conv("orientacao_origem_coerente"),
        ),
        CheckConstraint(
            "estado <> 'PONTUAL' OR origem = 'QUESTAO'",
            name=conv("pontual_so_de_questao"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sessao_id: Mapped[int] = mapped_column(ForeignKey("sessoes_geracao.id"), index=True)
    origem: Mapped[OrigemOrientacao] = mapped_column(
        SAEnum(OrigemOrientacao, name="origem_orientacao")
    )
    estado: Mapped[EstadoOrientacao] = mapped_column(
        SAEnum(EstadoOrientacao, name="estado_orientacao")
    )
    o_que_mudar: Mapped[str | None] = mapped_column(String(500))
    cruzar_com: Mapped[str | None] = mapped_column(String(200))
    banco_id: Mapped[int | None] = mapped_column(ForeignKey("bancos_questoes.id"))
    numero_origem: Mapped[int | None] = mapped_column(Integer)
    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
