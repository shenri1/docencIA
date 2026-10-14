"""questões de cálculo: formato CALCULO, p_calculo e prompt 2.3.0

Revision ID: e9c3a6d2f8b1
Revises: d8a4f1c6e3b2
Create Date: 2026-10-13

`ALTER TYPE … ADD VALUE` e a coluna `p_calculo` (padrão 0: sessões anteriores não
têm cálculo). Registra e ativa a 2.3.0 com os módulos em disco (objetiva/formatos/
calculo/ novo), pelo mesmo mecanismo da d8a4f1c6e3b2 e com o mesmo desvio
declarado (importa código do app). É minor: o schema de saída das outras formas
não muda. O downgrade não remove o valor do enum (o Postgres não permite) nem a
versão do prompt.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from backend.app.models.prompt_provedor import PromptMestre
from backend.app.prompt.parametros import ParametrosGeracao
from backend.app.services.prompt_mestre_service import ativar, registrar_versao

revision: str = "e9c3a6d2f8b1"
down_revision: str | None = "d8a4f1c6e3b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VERSAO = "2.3.0"
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
        if (
            db.scalar(sa.select(PromptMestre).where(PromptMestre.versao == VERSAO))
            is None
        ):
            registrar_versao(db, VERSAO, PAPEL, PARAMETROS_MARCADORES)
        ativar(db, VERSAO)


def upgrade() -> None:
    # O valor novo de enum não pode ser usado na mesma transação em que nasce, e
    # `ADD VALUE` não roda dentro de transação em PG < 12: o bloco autocommit
    # fecha a transação do Alembic antes do comando.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE formato_item ADD VALUE IF NOT EXISTS 'CALCULO'")
    op.add_column(
        "sessoes_geracao",
        sa.Column("p_calculo", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "calculo_entre_0_e_100", "sessoes_geracao", "p_calculo BETWEEN 0 AND 100"
    )
    _semear_prompt(op.get_bind())


def downgrade() -> None:
    op.drop_constraint("calculo_entre_0_e_100", "sessoes_geracao", type_="check")
    op.drop_column("sessoes_geracao", "p_calculo")
    # O Postgres não remove valor de enum: o 'CALCULO' órfão é inofensivo. A
    # versão do prompt pode já ter gerado questões e também fica.
