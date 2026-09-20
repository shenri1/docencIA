"""colunas de versionamento do prompt mestre

Revision ID: d3a8f1c04b62
Revises: c7e2a5b83f10
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3a8f1c04b62"
down_revision: str | None = "c7e2a5b83f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default temporário para preencher linhas existentes; sai em
    # seguida, porque o model não declara default de servidor para o hash.
    op.add_column(
        "prompts_mestres",
        sa.Column("hash_modulos", sa.String(length=64), nullable=False,
                  server_default=""),
    )
    op.alter_column("prompts_mestres", "hash_modulos", server_default=None)
    op.add_column(
        "prompts_mestres",
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_column("prompts_mestres", "criado_em")
    op.drop_column("prompts_mestres", "hash_modulos")
