"""Registro de consumo.

`calcular_custo` é Núcleo Determinístico: função pura, sem I/O. O registro
entra no adapter por uma porta injetada, e não como obrigação do chamador —
esquecer de registrar em um caminho deixaria incompleta sem sinal.
"""

from decimal import Decimal
from typing import Protocol

from sqlalchemy.orm import Session

from backend.app.models.prompt_provedor import ConsumoToken, ProvedorLLM
from backend.app.services.provedor.tipos import UsoTokens

_POR_MILHAO = Decimal(1_000_000)
# A coluna custo_estimado é Numeric(12, 6).
_CASAS = Decimal("0.000001")


def calcular_custo(uso: UsoTokens, provedor: ProvedorLLM) -> Decimal:
    """Preços são por milhão de tokens. Decimal porque é dinheiro."""
    entrada = Decimal(uso.entrada) * provedor.preco_input_por_milhao / _POR_MILHAO
    saida = Decimal(uso.saida) * provedor.preco_output_por_milhao / _POR_MILHAO
    return (entrada + saida).quantize(_CASAS)


class RegistradorConsumo(Protocol):
    def registrar(
        self, sessao_id: int, provedor: ProvedorLLM, uso: UsoTokens
    ) -> None: ...


class RegistradorConsumoDb:
    """ConsumoToken é append-only: só INSERT, nunca UPDATE."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def registrar(self, sessao_id: int, provedor: ProvedorLLM, uso: UsoTokens) -> None:
        self._db.add(
            ConsumoToken(
                sessao_id=sessao_id,
                provedor_id=provedor.id,
                tokens_input=uso.entrada,
                tokens_output=uso.saida,
                custo_estimado=calcular_custo(uso, provedor),
            )
        )
        self._db.commit()


class RegistradorConsumoFake:
    """Duplo determinístico: o adapter é testável sem Postgres."""

    def __init__(self) -> None:
        self.registros: list[tuple[int, int, UsoTokens]] = []

    def registrar(self, sessao_id: int, provedor: ProvedorLLM, uso: UsoTokens) -> None:
        self.registros.append((sessao_id, provedor.id, uso))
