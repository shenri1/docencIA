"""questões discursivas: tipo, aspectos esperados e contagem por tipo

Revision ID: a8d4e2f61c37
Revises: e5b2c9d71a40
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a8d4e2f61c37"
down_revision: str | None = "e5b2c9d71a40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JUSTIFICATIVA_OPCIONAL = (
    ("justificativa_correta", sa.Text()),
    ("invalidacao_distratores", postgresql.JSONB(astext_type=sa.Text())),
    ("verificacao_unicidade", sa.Boolean()),
    ("texto_verificacao_unicidade", sa.Text()),
)


def upgrade() -> None:
    tipo_questao = postgresql.ENUM("OBJETIVA", "DISCURSIVA", name="tipo_questao")
    tipo_questao.create(op.get_bind())
    # Default de servidor só para preencher as linhas existentes: toda questão
    # gerada até aqui é objetiva. Sai em seguida — o código sempre diz o tipo.
    op.add_column(
        "questoes",
        sa.Column(
            "tipo",
            sa.Enum("OBJETIVA", "DISCURSIVA", name="tipo_questao", create_type=False),
            nullable=False,
            server_default="OBJETIVA",
        ),
    )
    op.alter_column("questoes", "tipo", server_default=None)
    op.create_index(op.f("ix_questoes_tipo"), "questoes", ["tipo"])

    op.add_column(
        "bancos_questoes", sa.Column("n_alvo_objetivas", sa.Integer(), nullable=True)
    )
    op.add_column(
        "bancos_questoes", sa.Column("n_alvo_discursivas", sa.Integer(), nullable=True)
    )
    op.execute(
        "UPDATE bancos_questoes SET n_alvo_objetivas = n_alvo, n_alvo_discursivas = 0"
    )
    op.alter_column("bancos_questoes", "n_alvo_objetivas", nullable=False)
    op.alter_column("bancos_questoes", "n_alvo_discursivas", nullable=False)
    op.create_check_constraint(
        "n_alvo_soma_tipos",
        "bancos_questoes",
        "n_alvo = n_alvo_objetivas + n_alvo_discursivas",
    )

    for nome, tipo in _JUSTIFICATIVA_OPCIONAL:
        op.alter_column(
            "justificativas_estruturadas", nome, existing_type=tipo, nullable=True
        )

    op.create_table(
        "aspectos_esperados",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("questao_id", sa.Integer(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("fonte_interna_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["questao_id"],
            ["questoes.id"],
            name=op.f("fk_aspectos_esperados_questao_id_questoes"),
        ),
        sa.ForeignKeyConstraint(
            ["fonte_interna_id"],
            ["fontes_internas.id"],
            name=op.f("fk_aspectos_esperados_fonte_interna_id_fontes_internas"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_aspectos_esperados")),
        sa.UniqueConstraint("questao_id", "ordem", name="aspecto_por_questao_ordem"),
    )
    op.create_index(
        op.f("ix_aspectos_esperados_questao_id"), "aspectos_esperados", ["questao_id"]
    )

    op.add_column(
        "prompts_mestres", sa.Column("conteudo_discursiva", sa.Text(), nullable=True)
    )
    op.add_column(
        "prompts_mestres",
        sa.Column("conteudo_critico_discursiva", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("prompts_mestres", "conteudo_critico_discursiva")
    op.drop_column("prompts_mestres", "conteudo_discursiva")
    op.drop_index(
        op.f("ix_aspectos_esperados_questao_id"), table_name="aspectos_esperados"
    )
    op.drop_table("aspectos_esperados")
    # Justificativas de discursivas têm NULL nesses campos: voltar a NOT NULL
    # exige apagá-las antes, e o downgrade não apaga dados em silêncio.
    for nome, tipo in _JUSTIFICATIVA_OPCIONAL:
        op.alter_column(
            "justificativas_estruturadas", nome, existing_type=tipo, nullable=False
        )
    op.drop_constraint("n_alvo_soma_tipos", "bancos_questoes", type_="check")
    op.drop_column("bancos_questoes", "n_alvo_discursivas")
    op.drop_column("bancos_questoes", "n_alvo_objetivas")
    op.drop_index(op.f("ix_questoes_tipo"), table_name="questoes")
    op.drop_column("questoes", "tipo")
    postgresql.ENUM(name="tipo_questao").drop(op.get_bind())
