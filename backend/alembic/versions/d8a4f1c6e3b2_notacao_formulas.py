"""notação matemática e química: prompt 2.2.0

Revision ID: d8a4f1c6e3b2
Revises: c5e1f8a3b7d9
Create Date: 2026-10-13

Sem mudança de schema. Registra e ativa a 2.2.0 com os módulos em disco
(comum/06_notacao.md novo), pelo mesmo mecanismo da c5e1f8a3b7d9 e com o mesmo
desvio declarado (importa código do app). É minor: o schema de saída não muda.
Idempotente; o downgrade não apaga a versão, que pode já ter sido usada.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from backend.app.models.prompt_provedor import PromptMestre
from backend.app.prompt.parametros import ParametrosGeracao
from backend.app.services.prompt_mestre_service import ativar, registrar_versao

revision: str = "d8a4f1c6e3b2"
down_revision: str | None = "c5e1f8a3b7d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VERSAO = "2.2.0"
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
    _semear_prompt(op.get_bind())


def downgrade() -> None:
    # A versão pode já ter gerado questões: não se apaga.
    pass
