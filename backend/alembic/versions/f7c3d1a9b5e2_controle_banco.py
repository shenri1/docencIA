"""controle do banco: estados de questão, revisão e substituição

Revision ID: f7c3d1a9b5e2
Revises: a8d4e2f61c37
Create Date: 2026-09-26

Limitação registrada: o downgrade NÃO remove 'SUBSTITUIDA', 'CANDIDATA' e
'DESCARTADA' de `estado_questao`. O Postgres não suporta remover valor de enum.
Não afeta o funcionamento — é assimetria declarada, não esquecimento.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f7c3d1a9b5e2"
down_revision: str | None = "a8d4e2f61c37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOVOS_ESTADOS = ("SUBSTITUIDA", "CANDIDATA", "DESCARTADA")
_OCUPANTE = "estado IN ('ATIVA', 'EXCLUIDA')"
_CANDIDATA = "estado = 'CANDIDATA'"


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE não pode ser usado na mesma transação que o
    # criou, e o índice parcial do passo 4 referencia 'CANDIDATA'.
    with op.get_context().autocommit_block():
        for valor in _NOVOS_ESTADOS:
            op.execute(
                f"ALTER TYPE estado_questao ADD VALUE IF NOT EXISTS '{valor}'"
            )

    postgresql.ENUM(
        "EXCLUSAO", "SUBSTITUICAO", "CONGELAMENTO", name="evento_banco"
    ).create(op.get_bind())
    postgresql.ENUM("ACEITA", "REJEITADA", name="decisao_substituicao").create(
        op.get_bind()
    )

    # server_default fica: o model também o declara, e é o que preenche as
    # linhas de banco já existentes com revisão 0.
    op.add_column(
        "bancos_questoes",
        sa.Column("revisao", sa.Integer(), nullable=False, server_default="0"),
    )

    # Aqui o server_default é só para as linhas existentes e sai em seguida:
    # o código sempre diz a revisão, o evento e o alerta.
    op.add_column(
        "relatorios_impacto",
        sa.Column("revisao", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("relatorios_impacto", "revisao", server_default=None)
    op.add_column(
        "relatorios_impacto",
        sa.Column(
            "evento",
            postgresql.ENUM(
                "EXCLUSAO",
                "SUBSTITUICAO",
                "CONGELAMENTO",
                name="evento_banco",
                create_type=False,
            ),
            nullable=False,
            server_default="EXCLUSAO",
        ),
    )
    op.alter_column("relatorios_impacto", "evento", server_default=None)
    op.add_column(
        "relatorios_impacto",
        sa.Column(
            "alerta_desvio", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.alter_column("relatorios_impacto", "alerta_desvio", server_default=None)

    op.create_table(
        "registros_substituicao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("questao_original_id", sa.Integer(), nullable=False),
        sa.Column("candidata_id", sa.Integer(), nullable=False),
        sa.Column("docente_id", sa.Integer(), nullable=False),
        sa.Column(
            "decisao",
            # postgresql.ENUM, não sa.Enum: o Enum genérico ignora create_type e
            # emitiria CREATE TYPE de novo dentro do create_table.
            postgresql.ENUM(
                "ACEITA", "REJEITADA", name="decisao_substituicao", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["questao_original_id"],
            ["questoes.id"],
            name=op.f("fk_registros_substituicao_questao_original_id_questoes"),
        ),
        sa.ForeignKeyConstraint(
            ["candidata_id"],
            ["questoes.id"],
            name=op.f("fk_registros_substituicao_candidata_id_questoes"),
        ),
        sa.ForeignKeyConstraint(
            ["docente_id"],
            ["docentes.id"],
            name=op.f("fk_registros_substituicao_docente_id_docentes"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registros_substituicao")),
    )
    op.create_index(
        op.f("ix_registros_substituicao_questao_original_id"),
        "registros_substituicao",
        ["questao_original_id"],
    )

    op.drop_constraint("questao_por_banco_numero", "questoes", type_="unique")
    op.create_index(
        "questao_por_banco_numero_ocupado",
        "questoes",
        ["banco_id", "numero"],
        unique=True,
        postgresql_where=sa.text(_OCUPANTE),
    )
    op.create_index(
        "candidata_por_banco_numero",
        "questoes",
        ["banco_id", "numero"],
        unique=True,
        postgresql_where=sa.text(_CANDIDATA),
    )


def downgrade() -> None:
    op.drop_index("candidata_por_banco_numero", table_name="questoes")
    op.drop_index("questao_por_banco_numero_ocupado", table_name="questoes")
    # Só volta a ser possível se nenhum número tiver dois ocupantes — é o caso
    # depois de qualquer upgrade sem substituição aceita.
    op.create_unique_constraint(
        "questao_por_banco_numero", "questoes", ["banco_id", "numero"]
    )
    op.drop_index(
        op.f("ix_registros_substituicao_questao_original_id"),
        table_name="registros_substituicao",
    )
    op.drop_table("registros_substituicao")
    op.drop_column("relatorios_impacto", "alerta_desvio")
    op.drop_column("relatorios_impacto", "evento")
    op.drop_column("relatorios_impacto", "revisao")
    op.drop_column("bancos_questoes", "revisao")
    postgresql.ENUM(name="decisao_substituicao").drop(op.get_bind())
    postgresql.ENUM(name="evento_banco").drop(op.get_bind())
