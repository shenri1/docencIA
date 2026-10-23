"""qwen3.5:9b de volta à frente da cadeia; qwen2.5:3b-instruct desativado

Revision ID: a7d3e5b9c1f4
Revises: f2c8a4d1b6e7
Create Date: 2026-10-22

O teste da f2c8a4d1b6e7 reprovou o 3b: numa sessão de telecom, 16 de 20
números ficaram sem questão (fonte com identificador malformado, resposta
cortada em 2048 tokens), e a prova gerada trazia conteúdo copiado dos exemplos
do prompt (busca em largura), comandos de uma palavra e asserção idêntica à
razão. A cadeia volta à da a3f9c2e7d415. A linha do 3b só é desativada:
sessões e consumos de token podem apontar para ela por FK.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a7d3e5b9c1f4"
down_revision: str | None = "f2c8a4d1b6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE = [
    "UPDATE provedores_llm SET ativo = false WHERE nome = 'ollama-qwen2.5-3b'",
    "UPDATE provedores_llm SET prioridade = 1 WHERE nome = 'ollama-qwen3.5-9b'",
    "UPDATE provedores_llm SET prioridade = 2 WHERE nome = 'ollama-qwen3-4b'",
    "UPDATE provedores_llm SET prioridade = 3 WHERE nome = 'ollama-qwen3-1.7b'",
]

_DOWNGRADE = [
    "UPDATE provedores_llm SET ativo = true, prioridade = 1 "
    "WHERE nome = 'ollama-qwen2.5-3b'",
    "UPDATE provedores_llm SET prioridade = 2 WHERE nome = 'ollama-qwen3.5-9b'",
    "UPDATE provedores_llm SET prioridade = 3 WHERE nome = 'ollama-qwen3-4b'",
    "UPDATE provedores_llm SET prioridade = 4 WHERE nome = 'ollama-qwen3-1.7b'",
]


def upgrade() -> None:
    for comando in _UPGRADE:
        op.execute(comando)


def downgrade() -> None:
    for comando in _DOWNGRADE:
        op.execute(comando)
