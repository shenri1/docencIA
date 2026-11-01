"""métricas de geração por tentativa

Revision ID: b4e8c2f6a9d3
Revises: a7d3e5b9c1f4
Create Date: 2026-11-01

Cria `metricas_geracao`. CASCADE a partir do banco, para que o apagamento de
sessão da LGPD leve as métricas junto, e SET NULL a partir da questão. Sem
backfill: bancos anteriores ficam sem métricas, porque o tempo, os tokens e o
fluxo do RAG só existem durante a geração. 
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4e8c2f6a9d3"
down_revision: str | None = "a7d3e5b9c1f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "metricas_geracao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("banco_id", sa.Integer(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("questao_id", sa.Integer(), nullable=True),
        sa.Column("origem", sa.String(length=20), nullable=False),
        sa.Column("desfecho", sa.String(length=30), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("faixa", sa.String(length=30), nullable=False),
        sa.Column("formato_planejado", sa.String(length=30), nullable=False),
        sa.Column("formato_final", sa.String(length=30), nullable=True),
        sa.Column("motivo_recuo", sa.String(length=30), nullable=True),
        sa.Column("modelo_geracao", sa.String(length=100), nullable=True),
        sa.Column("modelo_revisao", sa.String(length=100), nullable=True),
        sa.Column("iniciada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tempos_ms", postgresql.JSONB(), nullable=False),
        sa.Column("tokens", postgresql.JSONB(), nullable=False),
        sa.Column("rag", postgresql.JSONB(), nullable=False),
        sa.Column("sustentacao", postgresql.JSONB(), nullable=True),
        sa.Column("aderencia", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ["banco_id"],
            ["bancos_questoes.id"],
            name=op.f("fk_metricas_geracao_banco_id_bancos_questoes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["questao_id"],
            ["questoes.id"],
            name=op.f("fk_metricas_geracao_questao_id_questoes"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metricas_geracao")),
    )
    op.create_index(
        op.f("ix_metricas_geracao_banco_id"), "metricas_geracao", ["banco_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_metricas_geracao_banco_id"), table_name="metricas_geracao")
    op.drop_table("metricas_geracao")
