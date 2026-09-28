"""montagem de provas A/B: vínculo com o banco e permutação por item

Revision ID: b9e4f2c76a18
Revises: f7c3d1a9b5e2
Create Date: 2026-09-26

Premissa declarada: `provas` e `itens_prova` estão VAZIAS. Elas existem desde a
migração inicial e nenhum código jamais as escreveu — `ItemProva.letra_atribuida`
nunca recebeu valor. Por isso as colunas novas entram NOT NULL sem
server_default e sem passo de preenchimento. Se algum ambiente tiver linhas ali,
o NOT NULL falha alto, que é o comportamento desejado: preencher por adivinhação
seria pior.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b9e4f2c76a18"
down_revision: str | None = "f7c3d1a9b5e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("provas", sa.Column("banco_id", sa.Integer(), nullable=False))
    op.create_foreign_key(
        op.f("fk_provas_banco_id_bancos_questoes"),
        "provas",
        "bancos_questoes",
        ["banco_id"],
        ["id"],
    )
    op.create_index(op.f("ix_provas_banco_id"), "provas", ["banco_id"])
    op.add_column("provas", sa.Column("revisao_banco", sa.Integer(), nullable=False))
    op.add_column("provas", sa.Column("n_objetivas", sa.Integer(), nullable=False))
    op.add_column("provas", sa.Column("n_discursivas", sa.Integer(), nullable=False))
    op.create_check_constraint(
        "n_questoes_soma_tipos",
        "provas",
        "n_questoes = n_objetivas + n_discursivas",
    )

    # Discursiva não tem letra: é sobre alternativas.
    op.alter_column(
        "itens_prova",
        "letra_atribuida",
        existing_type=sa.String(length=2),
        nullable=True,
    )
    op.add_column(
        "itens_prova",
        sa.Column(
            "ordem_alternativas",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("itens_prova", "ordem_alternativas")
    # Volta a NOT NULL: só é possível porque a tabela está vazia.
    op.alter_column(
        "itens_prova",
        "letra_atribuida",
        existing_type=sa.String(length=2),
        nullable=False,
    )
    op.drop_constraint("n_questoes_soma_tipos", "provas", type_="check")
    op.drop_column("provas", "n_discursivas")
    op.drop_column("provas", "n_objetivas")
    op.drop_column("provas", "revisao_banco")
    op.drop_index(op.f("ix_provas_banco_id"), table_name="provas")
    op.drop_constraint(
        op.f("fk_provas_banco_id_bancos_questoes"), "provas", type_="foreignkey"
    )
    op.drop_column("provas", "banco_id")
