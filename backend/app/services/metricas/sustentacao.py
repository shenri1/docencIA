"""Sustentação da citação no texto enviado ao Gerador — Núcleo
Determinístico. As métricas só registram; a recusa da fonte que não consta no
material é feita antes da gravação, em `resolver_fontes`, com `sustenta`.

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


# Abaixo disto o trecho citado não é tido como existente no chunk. Mesmo valor
# do LIMIAR_ASSERCAO_CITACAO do validador: cópia com pontuação ou hifenização
# diferente passa, paráfrase e invenção não.
LIMIAR_SUSTENTACAO = 0.8


# janela deslizante com passo len/4, O(n·m) por trecho; basta para
# chunks de ~1-2 mil caracteres. Trocar por rapidfuzz.partial_ratio se pesar.
# autojunk=False: com 200+ caracteres o padrão ignoraria as letras comuns e
# subestimaria a razão de citações longas.
def _melhor_janela(c: str, t: str) -> float:
    if len(t) <= len(c):
        return SequenceMatcher(None, c, t, autojunk=False).ratio()
    passo = max(1, len(c) // 4)
    return max(
        SequenceMatcher(None, c, t[i : i + len(c)], autojunk=False).ratio()
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


def sustenta(trecho_base: str, trecho: TrechoRecuperado) -> bool:
    """O `trecho_base` citado existe neste chunk (cópia literal normalizada ou
    similaridade a partir do limiar)?"""
    medida = medir_citacao(trecho_base, [trecho])
    return medida["literal"] or medida["similaridade"] >= LIMIAR_SUSTENTACAO


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
