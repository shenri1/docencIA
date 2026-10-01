"""Rerank — Núcleo Semântico.

O Qwen3-Reranker não tem cabeça de classificação: é um LM causal que responde
"yes" ou "no" a um prompt templado, e o score é a probabilidade relativa entre
os dois tokens. O `classifier_from_token: ["no", "yes"]` do vLLM só automatiza
isso. Como o Ollama expõe logprobs a partir da 0.12.11, o mesmo cálculo é
feito aqui, no cliente.

O modelo padrão é o `qwen3:1.7b`, não o Qwen3-Reranker: o GGUF
dengcao/Qwen3-Reranker-0.6B:Q8_0, chamado pelo /api/generate, devolve o mesmo
logprob (-ln do vocabulário) para todo token — distribuição uniforme, sem
"yes" nem "no". O Qwen3 comum segue o mesmo template e responde yes/no com
margem larga. `_uniforme` reconhece o sintoma e diz o que trocar.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from backend.app.core.config import settings
from backend.app.exceptions import FalhaRerankException

_TENTATIVAS = 3
_BACKOFF_BASE_S = 0.5
_TOP_LOGPROBS = 20

# Formato documentado do Qwen3-Reranker. Constante única: formato errado não
# gera erro, gera score ruim, então só existe um lugar para corrigir.
_TEMPLATE = (
    "<|im_start|>system\n"
    "Judge whether the Document meets the requirements based on the Query and "
    'the Instruct provided. Note that the answer can only be "yes" or "no".'
    "<|im_end|>\n"
    "<|im_start|>user\n"
    "<Instruct>: {instrucao}\n"
    "<Query>: {consulta}\n"
    "<Document>: {documento}<|im_end|>\n"
    "<|im_start|>assistant\n"
    "<think>\n\n</think>\n\n"
)


class Reranker(Protocol):
    def reordenar(
        self, consulta: str, documentos: list[str], top_n: int
    ) -> list[tuple[int, float]]: ...


@dataclass(frozen=True)
class ConfigRerank:
    base_url: str
    modelo: str
    instrucao: str
    timeout_s: float

    @classmethod
    def das_settings(cls) -> ConfigRerank:
        return cls(
            base_url=settings.rerank_base_url,
            modelo=settings.rerank_model,
            instrucao=settings.rerank_instrucao,
            timeout_s=settings.rerank_timeout_s,
        )


def _softmax_binario(lp_sim: float, lp_nao: float) -> float:
    maior = max(lp_sim, lp_nao)
    e_sim = math.exp(lp_sim - maior)
    e_nao = math.exp(lp_nao - maior)
    return e_sim / (e_sim + e_nao)


def _extrair_logprobs(dados: dict[str, Any]) -> tuple[float, float] | None:
    """Devolve (logprob de "yes", logprob de "no"), ou None se nenhum dos dois
    apareceu — sintoma de template errado, modelo errado ou Ollama antigo."""
    entradas = dados.get("logprobs")
    if not isinstance(entradas, list) or not entradas:
        return None
    primeira = entradas[0]
    encontrados: dict[str, float] = {}

    # O token efetivamente amostrado vem primeiro: o Ollama pode não repeti-lo
    # dentro de top_logprobs, e ignorá-lo faria o caso mais comum — "yes" com
    # alta confiança — virar None. top_logprobs só complementa o outro token.
    def registrar(token: str, logprob: float) -> None:
        token = token.strip().lower()
        if token in ("yes", "no") and token not in encontrados:
            encontrados[token] = logprob

    registrar(str(primeira.get("token", "")), float(primeira.get("logprob", 0.0)))
    for item in primeira.get("top_logprobs") or []:
        registrar(str(item.get("token", "")), float(item.get("logprob", 0.0)))

    if not encontrados:
        return None
    # Ausente no top-20 significa probabilidade desprezível, não zero.
    return encontrados.get("yes", -30.0), encontrados.get("no", -30.0)


def _uniforme(dados: dict[str, Any]) -> bool:
    """Todos os candidatos com o mesmo logprob: o modelo não está prevendo
    nada. É o que o GGUF dengcao/Qwen3-Reranker devolve pelo /api/generate —
    -ln(tamanho do vocabulário) para todo token."""
    entradas = dados.get("logprobs")
    if not isinstance(entradas, list) or not entradas:
        return False
    valores = [
        float(item.get("logprob", 0.0))
        for item in entradas[0].get("top_logprobs") or []
    ]
    return len(valores) > 1 and max(valores) - min(valores) < 1e-6


class RerankerOllamaLogprobs:
    def __init__(self, cfg: ConfigRerank, cliente: httpx.Client | None = None) -> None:
        self.cfg = cfg
        self._cliente = cliente or httpx.Client(
            base_url=cfg.base_url, timeout=cfg.timeout_s
        )

    def reordenar(
        self, consulta: str, documentos: list[str], top_n: int
    ) -> list[tuple[int, float]]:
        if not documentos:
            return []
        pontuados: list[tuple[int, float]] = []
        indecididos = 0
        uniformes = 0
        for indice, documento in enumerate(documentos):
            dados = self._pontuar(consulta, documento)
            par = _extrair_logprobs(dados)
            if par is None:
                indecididos += 1
                uniformes += _uniforme(dados)
                pontuados.append((indice, 0.0))
            else:
                pontuados.append((indice, _softmax_binario(*par)))
        if uniformes == len(documentos):
            raise FalhaRerankException(
                f"o modelo {self.cfg.modelo} devolve distribuição uniforme sobre "
                "o vocabulário: ele não gera texto pelo /api/generate. Troque "
                "RERANK_MODEL por um Qwen3 que gere texto (ex.: qwen3:1.7b)"
            )
        if indecididos == len(documentos):
            raise FalhaRerankException(
                "nenhum par produziu logprob de 'yes'/'no' — verifique o "
                "template, o modelo apontado em RERANK_MODEL e se o Ollama "
                "é >= 0.12.11"
            )
        pontuados.sort(key=lambda par: par[1], reverse=True)
        return pontuados[:top_n]

    def _pontuar(self, consulta: str, documento: str) -> dict[str, Any]:
        corpo = {
            "model": self.cfg.modelo,
            # raw desliga o template do Ollama: o prompt do reranker precisa
            # chegar exatamente como está montado aqui.
            "raw": True,
            "stream": False,
            "prompt": _TEMPLATE.format(
                instrucao=self.cfg.instrucao,
                consulta=consulta,
                documento=documento,
            ),
            "logprobs": True,
            "top_logprobs": _TOP_LOGPROBS,
            "options": {"num_predict": 1, "temperature": 0},
        }
        motivo = "sem resposta"
        for tentativa in range(_TENTATIVAS):
            try:
                resposta = self._cliente.post("/api/generate", json=corpo)
            except httpx.HTTPError as exc:
                motivo = type(exc).__name__
            else:
                if resposta.status_code < 500:
                    if resposta.status_code >= 400:
                        raise FalhaRerankException(f"HTTP {resposta.status_code}")
                    return resposta.json()
                motivo = f"HTTP {resposta.status_code}"
            if tentativa < _TENTATIVAS - 1:
                time.sleep(_BACKOFF_BASE_S * 2**tentativa)
        raise FalhaRerankException(motivo)


class RerankerFake:
    """Preserva a ordem de entrada com scores decrescentes. Um teste que
    quiser provar que a ordem final vem do reranker deve usar um duplo que
    inverte, não este."""

    def reordenar(
        self, consulta: str, documentos: list[str], top_n: int
    ) -> list[tuple[int, float]]:
        return [(i, 1.0 / (i + 1)) for i in range(len(documentos))][:top_n]


_reranker: RerankerOllamaLogprobs | None = None


def get_reranker() -> Reranker:
    """Dependência FastAPI. O cliente HTTP é singleton: um por processo, não
    um por requisição — senão cada busca vazaria pool de conexões e fds."""
    global _reranker
    if _reranker is None:
        _reranker = RerankerOllamaLogprobs(ConfigRerank.das_settings())
    return _reranker
