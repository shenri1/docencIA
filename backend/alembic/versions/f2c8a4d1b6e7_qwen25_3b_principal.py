"""qwen2.5:3b-instruct na frente da cadeia de fallback (teste)

Revision ID: f2c8a4d1b6e7
Revises: e9c3a6d2f8b1
Create Date: 2026-10-22

Teste de um modelo menor na geração: com o 3b na prioridade 1, ele e o
reranker (RERANK_MODEL, qwen3:1.7b, fora desta tabela) cabem juntos nos 8 GB
da RX 7600, sem descarregar um para carregar o outro a cada questão. O 9b, o
4b e o 1.7b seguem atrás, como reserva, nessa ordem. Decisão por impressão,
ainda não medida.

O qwen2.5 não tem modo de raciocínio. O cliente Ollama continua mandando
`think: false`, que é o valor neutro.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f2c8a4d1b6e7"
down_revision: str | None = "e9c3a6d2f8b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Upsert, pelo mesmo motivo da a3f9c2e7d415: o downgrade só desativa a linha
# (sessões e consumos de token podem apontar para ela por FK).
_UPGRADE = [
    """
    INSERT INTO provedores_llm
        (nome, modelo, tipo, endpoint, preco_input_por_milhao,
         preco_output_por_milhao, janela_contexto, ativo,
         referencia_chave_secrets, prioridade)
    VALUES
        ('ollama-qwen2.5-3b', 'qwen2.5:3b-instruct', 'LOCAL', NULL, 0, 0, 32768,
         true, NULL, 1)
    ON CONFLICT (nome) DO UPDATE
        SET modelo = EXCLUDED.modelo, ativo = true, prioridade = 1
    """,
    "UPDATE provedores_llm SET prioridade = 2 WHERE nome = 'ollama-qwen3.5-9b'",
    "UPDATE provedores_llm SET prioridade = 3 WHERE nome = 'ollama-qwen3-4b'",
    "UPDATE provedores_llm SET prioridade = 4 WHERE nome = 'ollama-qwen3-1.7b'",
]

_DOWNGRADE = [
    "UPDATE provedores_llm SET ativo = false WHERE nome = 'ollama-qwen2.5-3b'",
    "UPDATE provedores_llm SET prioridade = 1 WHERE nome = 'ollama-qwen3.5-9b'",
    "UPDATE provedores_llm SET prioridade = 2 WHERE nome = 'ollama-qwen3-4b'",
    "UPDATE provedores_llm SET prioridade = 3 WHERE nome = 'ollama-qwen3-1.7b'",
]


def upgrade() -> None:
    for comando in _UPGRADE:
        op.execute(comando)


def downgrade() -> None:
    for comando in _DOWNGRADE:
        op.execute(comando)
