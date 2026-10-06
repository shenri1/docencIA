"""qwen3.5:9b na frente da cadeia de fallback

Revision ID: a3f9c2e7d415
Revises: e1a4c8f02b77
Create Date: 2026-10-06

O 9b vira prioridade 1; o qwen3:4b e o qwen3:1.7b seguem atrás, como reserva.
O reranker (RERANK_MODEL, qwen3:1.7b) não passa por esta tabela e não muda.

Com 8 GB de VRAM, o 9b ocupa quase toda a placa: o 4b e o 1.7b só são
carregados se o 9b falhar. 
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a3f9c2e7d415"
down_revision: str | None = "e1a4c8f02b77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Upsert: o downgrade só desativa a linha (sessões e consumos de token podem
# apontar para ela por FK), então subir de novo precisa reativá-la.
_UPGRADE = [
    """
    INSERT INTO provedores_llm
        (nome, modelo, tipo, endpoint, preco_input_por_milhao,
         preco_output_por_milhao, janela_contexto, ativo,
         referencia_chave_secrets, prioridade)
    VALUES
        ('ollama-qwen3.5-9b', 'qwen3.5:9b', 'LOCAL', NULL, 0, 0, 262144,
         true, NULL, 1)
    ON CONFLICT (nome) DO UPDATE
        SET modelo = EXCLUDED.modelo, ativo = true, prioridade = 1
    """,
    # As tags são regravadas, não só as prioridades: trocar de modelo é
    # migração, e uma edição manual da linha (ex.: qwen3:latest, que é o 8b)
    # deixaria a reserva maior que a placa.
    "UPDATE provedores_llm SET modelo = 'qwen3:4b', prioridade = 2 "
    "WHERE nome = 'ollama-qwen3-4b'",
    "UPDATE provedores_llm SET modelo = 'qwen3:1.7b', prioridade = 3 "
    "WHERE nome = 'ollama-qwen3-1.7b'",
]

_DOWNGRADE = [
    "UPDATE provedores_llm SET ativo = false WHERE nome = 'ollama-qwen3.5-9b'",
    "UPDATE provedores_llm SET prioridade = 1 WHERE nome = 'ollama-qwen3-4b'",
    "UPDATE provedores_llm SET prioridade = 2 WHERE nome = 'ollama-qwen3-1.7b'",
]


def upgrade() -> None:
    for comando in _UPGRADE:
        op.execute(comando)


def downgrade() -> None:
    for comando in _DOWNGRADE:
        op.execute(comando)
