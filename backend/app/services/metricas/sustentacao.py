"""Sustentação da citação no texto enviado ao Gerador — Núcleo
Determinístico. Só registra: a continua em `resolver_fontes`.

Compara o `trecho_base` que o modelo citou com o texto dos trechos que ele
recebeu. Separa cópia literal de paráfrase próxima e de invenção.
"""

from __future__ import annotations

from collections.abc import Sequence
from difflib import SequenceMatcher

from backend.app.services.rag.retrieval_service import TrechoRecuperado

_TRADUCAO = str.maketrans(
    {"“": '"', "”": '"', "«": '"', "»": '"', "‘": "'", "’": "'",
     "–": "-", "—": "-", "‐": "-"}
)  # fmt: skip


def normalizar(texto: str) -> str:
    return " ".join(texto.lower().translate(_TRADUCAO).split())


# ponytail: janela deslizante com passo len/4, O(n·m) por trecho; basta para
# chunks de ~1-2 mil caracteres. Trocar por rapidfuzz.partial_ratio se pesar.
def _melhor_janela(c: str, t: str) -> float:
    if len(t) <= len(c):
        return SequenceMatcher(None, c, t).ratio()
    passo = max(1, len(c) // 4)
    return max(
        SequenceMatcher(None, c, t[i : i + len(c)]).ratio()
        for i in range(0, len(t) - len(c) + 1, passo)
    )


def medir_citacao(trecho_base: str, trechos: Sequence[TrechoRecuperado]) -> dict:
    c = normalizar(trecho_base)
    melhor, chunk_id = 0.0, None
    for trecho in trechos:
        t = normalizar(trecho.texto)
        if c and c in t:
            return {"literal": True, "similaridade": 1.0, "chunk_id": trecho.chunk_id}
        similaridade = _melhor_janela(c, t) if c and t else 0.0
        if similaridade > melhor or chunk_id is None:
            melhor, chunk_id = similaridade, trecho.chunk_id
    return {"literal": False, "similaridade": round(melhor, 3), "chunk_id": chunk_id}


def medir_sustentacao(questao, trechos: Sequence[TrechoRecuperado]) -> list[dict]:
    """Um item por fonte interna. Na discursiva os aspectos apontam para essas
    mesmas fontes, então nada mais é preciso."""
    return [
        {
            "fonte_id": f.id,
            "material_id": f.material_id,
            "localizacao": f.localizacao,
            **medir_citacao(f.trecho_base, trechos),
        }
        for f in questao.fontes_internas
    ]
