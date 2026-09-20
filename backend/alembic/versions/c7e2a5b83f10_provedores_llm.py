"""colunas de provedor LLM e seed da cadeia de fallback

Revision ID: c7e2a5b83f10
Revises: b1f4c7a9d2e3
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7e2a5b83f10"
down_revision: str | None = "b1f4c7a9d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# O SAEnum do projeto persiste o NOME do membro, não o valor: 'LOCAL', não
# 'local'. Conferir na migração inicial, que grava 'DOCENTE'/'COORDENADOR'.
_SEED = """
    INSERT INTO provedores_llm
        (nome, modelo, tipo, endpoint, preco_input_por_milhao,
         preco_output_por_milhao, janela_contexto, ativo,
         referencia_chave_secrets, prioridade)
    VALUES
        ('ollama-qwen3-4b', 'qwen3:4b', 'LOCAL', NULL, 0, 0, 262144,
         true, NULL, 1),
        ('ollama-qwen3-1.7b', 'qwen3:1.7b', 'LOCAL', NULL, 0, 0, 40960,
         true, NULL, 2)
"""


def upgrade() -> None:
    # server_default temporário para preencher linhas existentes; sai em
    # seguida, porque o model não declara default de servidor.
    op.add_column(
        "provedores_llm",
        sa.Column("modelo", sa.String(length=100), nullable=False, server_default=""),
    )
    op.alter_column(
        "provedores_llm",
        "modelo",
        existing_type=sa.String(length=100),
        server_default=None,
    )

    op.add_column(
        "provedores_llm",
        sa.Column("prioridade", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column(
        "provedores_llm",
        "prioridade",
        existing_type=sa.Integer(),
        server_default=None,
    )
    op.create_index(
        op.f("ix_provedores_llm_prioridade"),
        "provedores_llm",
        ["prioridade"],
        unique=False,
    )

    op.alter_column(
        "provedores_llm",
        "referencia_chave_secrets",
        existing_type=sa.String(length=255),
        nullable=True,
    )

    op.execute(_SEED)


def downgrade() -> None:
    # Apagar a seed ANTES de voltar a coluna para NOT NULL: as linhas de seed
    # têm referencia_chave_secrets NULL e bloqueariam o ALTER.
    op.execute(
        "DELETE FROM provedores_llm "
        "WHERE nome IN ('ollama-qwen3-4b', 'ollama-qwen3-1.7b')"
    )
    op.alter_column(
        "provedores_llm",
        "referencia_chave_secrets",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.drop_index(op.f("ix_provedores_llm_prioridade"), table_name="provedores_llm")
    op.drop_column("provedores_llm", "prioridade")
    op.drop_column("provedores_llm", "modelo")
