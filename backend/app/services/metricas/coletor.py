"""Acumulador das métricas de uma tentativa — Núcleo Determinístico.

Só acumula: não grava nem chama modelo. Quem grava é `registro.py`, depois que
a questão já foi commitada.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from backend.app.domain import FormatoItem
from backend.app.services.provedor.tipos import UsoTokens

if TYPE_CHECKING:
    from backend.app.services.rag.retrieval_service import TrechoRecuperado

_CONSULTA_MAX = 500


@dataclass
class Coletor:
    relogio: Callable[[], float] = time.perf_counter
    iniciada_em: datetime = field(default_factory=lambda: datetime.now(UTC))
    tempos_ms: dict[str, Any] = field(default_factory=dict)
    tokens: list[dict] = field(default_factory=list)
    rag: list[dict] = field(default_factory=list)
    # Contexto da tentativa, preenchido por `_produzir_questao`.
    formato_final: FormatoItem | None = None
    motivo_recuo: str | None = None
    modelo_geracao: str | None = None
    modelo_revisao: str | None = None
    trechos_enviados: list[TrechoRecuperado] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._inicio = self.relogio()

    @contextmanager
    def medir(self, etapa: str, formato: FormatoItem | None = None) -> Iterator[None]:
        """Sem `formato`, soma em `tempos_ms[etapa]`; com ele, acrescenta uma
        entrada por tentativa de formato."""
        inicio = self.relogio()
        try:
            yield
        finally:
            ms = round((self.relogio() - inicio) * 1000)
            if formato is None:
                self.tempos_ms[etapa] = self.tempos_ms.get(etapa, 0) + ms
            else:
                self.tempos_ms.setdefault(etapa, []).append(
                    {"formato": formato.value, "ms": ms}
                )

    def anotar_tokens(
        self,
        papel: str,
        uso: UsoTokens,
        modelo: str,
        formato: FormatoItem | None = None,
    ) -> None:
        self.tokens.append(
            {
                "papel": papel,
                "formato": formato.value if formato else None,
                "modelo": modelo,
                "entrada": uso.entrada,
                "saida": uso.saida,
            }
        )

    def anotar_busca(self, origem: str, consulta: str, candidatos: list[dict]) -> None:
        self.rag.append(
            {
                "origem": origem,
                "consulta": consulta[:_CONSULTA_MAX],
                "candidatos": candidatos,
            }
        )

    def fechar(self) -> None:
        self.tempos_ms["total"] = round((self.relogio() - self._inicio) * 1000)
        enviados = {t.chunk_id for t in self.trechos_enviados}
        for busca in self.rag:
            for candidato in busca["candidatos"]:
                candidato["enviado"] = candidato["chunk_id"] in enviados
