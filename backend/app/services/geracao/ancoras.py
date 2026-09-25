"""Seleção de âncoras — Núcleo Determinístico, nunca chama LLM.

Cada questão nasce ancorada num chunk específico. Isso resolve o problema de
"sobre o que perguntar" sem delegá-lo ao modelo: garante cobertura do material
inteiro e torna a fonte primária conhecida antes da chamada.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.exceptions import MaterialInsuficienteParaBancoException
from backend.app.models.identidade import SessaoGeracao
from backend.app.models.materiais import ChunkMaterial, MaterialReferencia


def selecionar_ancoras(
    db: Session, sessao: SessaoGeracao, n: int
) -> list[ChunkMaterial]:
    chunks = list(
        db.scalars(
            select(ChunkMaterial)
            .join(
                MaterialReferencia,
                ChunkMaterial.material_id == MaterialReferencia.id,
            )
            # A cláusula que implementa a R2 na ancoragem: nenhum chunk de
            # outra sessão pode virar âncora.
            .where(MaterialReferencia.sessao_id == sessao.id)
            .order_by(ChunkMaterial.material_id, ChunkMaterial.ordem)
        )
    )

    total = len(chunks)
    if total < n:
        raise MaterialInsuficienteParaBancoException(chunks=total, pedidos=n)

    # Espaçamento uniforme. Como total >= n, i * total // n é estritamente
    # crescente, então duas âncoras nunca coincidem.
    return [chunks[i * total // n] for i in range(n)]
