"""contextualização e formatos de item: formato, estrutura do formato,
item do aspecto e prompt mestre 2.0.0

Revision ID: b7d2e9f4a1c6
Revises: a3f9c2e7d415
Create Date: 2026-10-08

`formato` nasce NOT NULL com server_default='PROPOSICAO' só durante o ADD
COLUMN, para o upgrade passar num banco que já tem questões — elas são
proposição. O default sai em seguida: nenhuma questão nova nasce sem o formato
escolhido pelo plano.

Prompt: registra e ativa a 2.0.0 com os módulos em disco, pelo mesmo mecanismo
da e1a4c8f02b77 e com o mesmo desvio declarado (importa código do app). É major
porque o schema de saída mudou. Idempotente; o downgrade não apaga a versão,
que pode já ter sido usada.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from backend.app.models.prompt_provedor import PromptMestre
from backend.app.prompt.parametros import ParametrosGeracao
from backend.app.services.prompt_mestre_service import ativar, registrar_versao

revision: str = "b7d2e9f4a1c6"
down_revision: str | None = "a3f9c2e7d415"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VERSAO = "2.0.0"
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
_FORMATOS = ("PROPOSICAO", "AFIRMATIVAS", "ASSERCAO_RAZAO")


def _semear_prompt(conexao: sa.Connection) -> None:
    with Session(bind=conexao) as db:
        if (
            db.scalar(sa.select(PromptMestre).where(PromptMestre.versao == VERSAO))
            is None
        ):
            registrar_versao(db, VERSAO, PAPEL, PARAMETROS_MARCADORES)
        ativar(db, VERSAO)


def upgrade() -> None:
    postgresql.ENUM(*_FORMATOS, name="formato_item").create(op.get_bind())
    op.add_column(
        "questoes",
        sa.Column(
            "formato",
            sa.Enum(*_FORMATOS, name="formato_item", create_type=False),
            nullable=False,
            server_default="PROPOSICAO",
        ),
    )
    op.alter_column("questoes", "formato", server_default=None)
    op.add_column(
        "justificativas_estruturadas",
        sa.Column(
            "estrutura_formato", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.add_column("aspectos_esperados", sa.Column("item", sa.Integer(), nullable=True))
    _semear_prompt(op.get_bind())


def downgrade() -> None:
    op.drop_column("aspectos_esperados", "item")
    op.drop_column("justificativas_estruturadas", "estrutura_formato")
    op.drop_column("questoes", "formato")
    postgresql.ENUM(name="formato_item").drop(op.get_bind())
