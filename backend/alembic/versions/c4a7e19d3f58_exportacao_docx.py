"""exportação DOCX: revisão, data e unicidade do registro

Revision ID: c4a7e19d3f58
Revises: b9e4f2c76a18
Create Date: 2026-09-29

Premissa declarada: `exportacoes_docx` está VAZIA. Ela existe desde a migração
inicial e nenhum código jamais a escreveu. Por isso `revisao_banco` entra NOT
NULL sem server_default e sem passo de preenchimento — mesma premissa da
migração sobre `provas`. Se houver linha, falha alto, que é o
desejado: preencher a revisão de um arquivo já entregue seria inventá-la.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4a7e19d3f58"
down_revision: str | None = "b9e4f2c76a18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "exportacoes_docx", sa.Column("revisao_banco", sa.Integer(), nullable=False)
    )
    # server_default fica: o model também o declara.
    op.add_column(
        "exportacoes_docx",
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "exportacao_por_banco_revisao_tipo",
        "exportacoes_docx",
        ["banco_id", "revisao_banco", "tipo"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "exportacao_por_banco_revisao_tipo", "exportacoes_docx", type_="unique"
    )
    op.drop_column("exportacoes_docx", "criado_em")
    op.drop_column("exportacoes_docx", "revisao_banco")
