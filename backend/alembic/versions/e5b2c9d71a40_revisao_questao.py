"""revisão da questão e texto do prompt do crítico

Revision ID: e5b2c9d71a40
Revises: d3a8f1c04b62
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5b2c9d71a40"
down_revision: str | None = "d3a8f1c04b62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "revisoes_questao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("questao_id", sa.Integer(), nullable=False),
        sa.Column("rascunho", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "violacoes_rascunho",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "violacoes_final", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("modelo_geracao", sa.String(length=100), nullable=False),
        sa.Column("modelo_revisao", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(
            ["questao_id"],
            ["questoes.id"],
            name=op.f("fk_revisoes_questao_questao_id_questoes"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_revisoes_questao")),
    )
    op.create_index(
        op.f("ix_revisoes_questao_questao_id"),
        "revisoes_questao",
        ["questao_id"],
        unique=True,
    )
    op.add_column(
        "prompts_mestres", sa.Column("conteudo_critico", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("prompts_mestres", "conteudo_critico")
    op.drop_index(
        op.f("ix_revisoes_questao_questao_id"), table_name="revisoes_questao"
    )
    op.drop_table("revisoes_questao")
