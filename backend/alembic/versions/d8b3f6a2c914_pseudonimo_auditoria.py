"""Pseudonimiza o ator das auditorias legadas.

Correção única de conformidade. parte B gravava a credencial
institucional em texto puro em `registros_auditoria.ator`; daqui em diante o
ator é `pseudonimo(docente_id)`. Esta migração reescreve as linhas antigas de
`auditoria_questao`:

- credencial de docente existente -> pseudônimo do id;
- credencial sem docente e sem forma de pseudônimo -> NULL;
- valor que já tem forma de pseudônimo (64 hex minúsculos) -> não toca.

A regra da forma torna a migração idempotente: sem ela, rodar de novo
anularia os pseudônimos, que não casam com credencial nenhuma. Credencial
institucional com forma de 64 hex seria mantida; o cadastro não impede isso,
e o caso está declarado.

Escreve por SQL direto: `append_only` é evento do ORM, não trigger no banco.
Não é precedente para editar o log.

Usa a PSEUDONIMO_KEY do ambiente em que roda, que tem de ser a mesma da API.

Revision ID: d8b3f6a2c914
Revises: c4a7e19d3f58
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from backend.app.services.log_auditoria import pseudonimo

revision: str = "d8b3f6a2c914"
down_revision: str | None = "c4a7e19d3f58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FORMA_DE_PSEUDONIMO = re.compile(r"^[0-9a-f]{64}$")


def upgrade() -> None:
    conexao = op.get_bind()
    linhas = conexao.execute(
        sa.text(
            "SELECT r.id, r.ator, d.id FROM registros_auditoria r "
            "LEFT JOIN docentes d ON d.credencial_institucional = r.ator "
            "WHERE r.tipo_evento = 'auditoria_questao' AND r.ator IS NOT NULL"
        )
    ).all()
    for registro_id, ator, docente_id in linhas:
        if docente_id is not None:
            novo = pseudonimo(docente_id)
        elif _FORMA_DE_PSEUDONIMO.match(ator):
            continue
        else:
            novo = None
        conexao.execute(
            sa.text("UPDATE registros_auditoria SET ator = :a WHERE id = :i"),
            {"a": novo, "i": registro_id},
        )


def downgrade() -> None:
    # No-op declarado: o pseudônimo não se inverte.
    pass
