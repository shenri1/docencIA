"""colunas de indexação RAG e dimensão do vetor

Revision ID: b1f4c7a9d2e3
Revises: 8cdda0fc58d8
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1f4c7a9d2e3"
down_revision: str | None = "8cdda0fc58d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "materiais_referencia",
        sa.Column("indexado_em", sa.DateTime(timezone=True), nullable=True),
    )
    # server_default temporário só para preencher linhas existentes; sai em
    # seguida, porque o model declara o default do lado do Python.
    op.add_column(
        "materiais_referencia",
        sa.Column("n_chunks", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("materiais_referencia", "n_chunks", server_default=None)

    op.add_column(
        "chunks_material",
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("chunks_material", "ordem", server_default=None)
    op.create_unique_constraint(
        "chunk_por_material_ordem", "chunks_material", ["material_id", "ordem"]
    )

    # O índice HNSW é construído em cima do tipo da coluna: precisa cair antes
    # do ALTER e ser recriado depois. A tabela está vazia, então não há
    # conversão de dado — vetores de dimensões diferentes não são comparáveis
    # de qualquer forma.
    op.drop_index("ix_chunks_material_embedding_hnsw", table_name="chunks_material")
    op.execute(
        "ALTER TABLE chunks_material ALTER COLUMN vetor_embedding TYPE vector(1024)"
    )
    op.create_index(
        "ix_chunks_material_embedding_hnsw",
        "chunks_material",
        ["vetor_embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"vetor_embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_material_embedding_hnsw", table_name="chunks_material")
    op.execute(
        "ALTER TABLE chunks_material ALTER COLUMN vetor_embedding TYPE vector(1536)"
    )
    op.create_index(
        "ix_chunks_material_embedding_hnsw",
        "chunks_material",
        ["vetor_embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"vetor_embedding": "vector_cosine_ops"},
    )
    op.drop_constraint("chunk_por_material_ordem", "chunks_material", type_="unique")
    op.drop_column("chunks_material", "ordem")
    op.drop_column("materiais_referencia", "n_chunks")
    op.drop_column("materiais_referencia", "indexado_em")
