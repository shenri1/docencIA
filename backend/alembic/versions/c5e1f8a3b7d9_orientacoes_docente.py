"""orientações do docente: orientacoes_docente e questoes_orientacoes

Revision ID: c5e1f8a3b7d9
Revises: b7d2e9f4a1c6
Create Date: 2026-10-13

Só tabelas novas: nenhuma coluna em tabela existente. Questões anteriores à
etapa simplesmente não têm ligação, e a leitura devolve a lista vazia.

Prompt: registra e ativa a 2.1.0 com os módulos em disco (comum/05_orientacoes.md
novo), pelo mesmo mecanismo da b7d2e9f4a1c6 e com o mesmo desvio declarado
(importa código do app). É minor: o schema de saída não muda. Idempotente; o
downgrade não apaga a versão, que pode já ter sido usada.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from backend.app.models.prompt_provedor import PromptMestre
from backend.app.prompt.parametros import ParametrosGeracao
from backend.app.services.prompt_mestre_service import ativar, registrar_versao

revision: str = "c5e1f8a3b7d9"
down_revision: str | None = "b7d2e9f4a1c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ORIGENS = ("SESSAO", "QUESTAO")
_ESTADOS = ("ATIVA", "INATIVA", "PONTUAL")

VERSAO = "2.1.0"
PAPEL = "docente universitário elaborador de questões"
# Mesmos marcadores da e1a4c8f02b77: a geração reinjeta os parâmetros da sessão.
PARAMETROS_MARCADORES = ParametrosGeracao(
    disciplina="(definida em cada sessão)",
    periodo="(definido em cada sessão)",
    area_do_conhecimento=None,
    tema_escopo=None,
    k_alternativas=5,
    n_faceis=0,
    n_medias=0,
    n_dificeis=0,
)


def _semear_prompt(conexao: sa.Connection) -> None:
    with Session(bind=conexao) as db:
        if db.scalar(sa.select(PromptMestre).where(PromptMestre.versao == VERSAO)) is None:
            registrar_versao(db, VERSAO, PAPEL, PARAMETROS_MARCADORES)
        ativar(db, VERSAO)


def upgrade() -> None:
    postgresql.ENUM(*_ORIGENS, name="origem_orientacao").create(op.get_bind())
    postgresql.ENUM(*_ESTADOS, name="estado_orientacao").create(op.get_bind())

    op.create_table(
        "orientacoes_docente",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sessao_id", sa.Integer(), nullable=False),
        sa.Column(
            "origem",
            postgresql.ENUM(*_ORIGENS, name="origem_orientacao", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "estado",
            postgresql.ENUM(*_ESTADOS, name="estado_orientacao", create_type=False),
            nullable=False,
        ),
        sa.Column("o_que_mudar", sa.String(length=500), nullable=True),
        sa.Column("cruzar_com", sa.String(length=200), nullable=True),
        sa.Column("banco_id", sa.Integer(), nullable=True),
        sa.Column("numero_origem", sa.Integer(), nullable=True),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "o_que_mudar IS NOT NULL OR cruzar_com IS NOT NULL",
            name="orientacao_tem_texto",
        ),
        sa.CheckConstraint(
            "(origem = 'SESSAO' AND banco_id IS NULL AND numero_origem IS NULL "
            "AND cruzar_com IS NULL) OR (origem = 'QUESTAO' AND banco_id IS NOT "
            "NULL AND numero_origem IS NOT NULL)",
            name="orientacao_origem_coerente",
        ),
        sa.CheckConstraint(
            "estado <> 'PONTUAL' OR origem = 'QUESTAO'",
            name="pontual_so_de_questao",
        ),
        sa.ForeignKeyConstraint(
            ["sessao_id"],
            ["sessoes_geracao.id"],
            name=op.f("fk_orientacoes_docente_sessao_id_sessoes_geracao"),
        ),
        sa.ForeignKeyConstraint(
            ["banco_id"],
            ["bancos_questoes.id"],
            name=op.f("fk_orientacoes_docente_banco_id_bancos_questoes"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orientacoes_docente")),
    )
    op.create_index(
        op.f("ix_orientacoes_docente_sessao_id"),
        "orientacoes_docente",
        ["sessao_id"],
        unique=False,
    )
    op.create_table(
        "questoes_orientacoes",
        sa.Column("questao_id", sa.Integer(), nullable=False),
        sa.Column("orientacao_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["questao_id"],
            ["questoes.id"],
            name=op.f("fk_questoes_orientacoes_questao_id_questoes"),
        ),
        sa.ForeignKeyConstraint(
            ["orientacao_id"],
            ["orientacoes_docente.id"],
            name=op.f("fk_questoes_orientacoes_orientacao_id_orientacoes_docente"),
        ),
        sa.PrimaryKeyConstraint(
            "questao_id", "orientacao_id", name=op.f("pk_questoes_orientacoes")
        ),
    )
    _semear_prompt(op.get_bind())


def downgrade() -> None:
    op.drop_table("questoes_orientacoes")
    op.drop_index(
        op.f("ix_orientacoes_docente_sessao_id"), table_name="orientacoes_docente"
    )
    op.drop_table("orientacoes_docente")
    postgresql.ENUM(name="estado_orientacao").drop(op.get_bind())
    postgresql.ENUM(name="origem_orientacao").drop(op.get_bind())
