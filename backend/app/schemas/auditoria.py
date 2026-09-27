"""Schema da SAÍDA do modelo na auditoria.

Não confundir com schema de resposta da API, que fica em `schemas/banco.py`.

Construído por chamada, e não uma vez, porque duas restrições dependem do
contexto: as letras válidas dependem de K, e as localizações citáveis dependem
dos trechos que o retrieval trouxe. Fechar as duas por enum é a lição do
`nivel_bloom` da o que a decodificação restrita do Ollama pode impor
não deve ser conferido depois.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, create_model

from backend.app.domain import RiscoAuditoria
from backend.app.schemas.geracao import K_MAXIMO, K_MINIMO, LETRAS

# O modelo emite só os dois riscos semânticos. `assimetria_forma` é medida pelo
# código, e deixá-la no Literal permitiria ao modelo reivindicar um achado que
# não é dele.
RISCOS_DO_MODELO: tuple[str, ...] = (
    RiscoAuditoria.CORRETA_NAO_UNICA.value,
    RiscoAuditoria.DISTRATOR_INDEFENSAVEL.value,
)


def montar_schema_auditoria(k: int, localizacoes: list[str]) -> type[BaseModel]:
    if not K_MINIMO <= k <= K_MAXIMO:
        raise ValueError(f"k deve estar entre {K_MINIMO} e {K_MAXIMO}, recebido {k}")
    # dict.fromkeys preserva a ordem de chegada e remove repetição: dois chunks
    # da mesma página dariam valor duplicado, e Literal exige valores distintos.
    unicas = tuple(dict.fromkeys(localizacoes))
    if not unicas:
        raise ValueError(
            "localizacoes não pode ser vazia — `buscar` sobre índice confirmado "
            "devolve ao menos um trecho, então isto é erro de programação"
        )
    achado = create_model(
        f"AchadoGerado{k}",
        risco=(Literal[RISCOS_DO_MODELO], ...),
        alvo=(Literal[tuple(LETRAS[:k])], ...),
        localizacao=(Literal[unicas], ...),
        trecho_fonte=(str, ...),
        proposta_ajuste=(str, ...),
    )
    # Sem min_length: lista vazia é o caso comum e correto.
    return create_model(f"ResultadoAuditoria{k}", achados=(list[achado], ...))
