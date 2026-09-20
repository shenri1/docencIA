"""Embeddings — Núcleo Semântico: fala com um modelo, atrás de um Protocol.

O código da API não sabe que existe Ollama: sabe que existe uma URL que fala
o dialeto de embeddings da OpenAI. Trocar de motor é escrever outra classe e
mudar uma variável de ambiente.
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from backend.app.core.config import settings
from backend.app.exceptions import (
    ConfiguracaoEmbeddingInvalidaException,
    FalhaEmbeddingException,
)

_TENTATIVAS = 3
_BACKOFF_BASE_S = 0.5


class Embeddings(Protocol):
    dimensao: int

    def embutir_documentos(self, textos: list[str]) -> list[list[float]]: ...
    def embutir_consulta(self, texto: str) -> list[float]: ...


@dataclass(frozen=True)
class ConfigEmbeddings:
    base_url: str
    modelo: str
    instrucao_consulta: str
    instrucao_documento: str
    lote: int
    timeout_s: float
    dimensao: int

    @classmethod
    def das_settings(cls) -> ConfigEmbeddings:
        return cls(
            base_url=settings.embedding_base_url,
            modelo=settings.embedding_model,
            instrucao_consulta=settings.embedding_instrucao_consulta,
            instrucao_documento=settings.embedding_instrucao_documento,
            lote=settings.embedding_batch,
            timeout_s=settings.embedding_timeout_s,
            dimensao=settings.embedding_dim,
        )


def normalizar(vetor: list[float]) -> list[float]:
    """Divide pela norma L2. A distância de cosseno do pgvector ordena errado
    com vetor não normalizado; vetor nulo fica como está — detectar isso é
    responsabilidade do chamador, não de uma função de álgebra linear."""
    norma = math.sqrt(sum(v * v for v in vetor))
    if norma == 0.0:
        return vetor
    return [v / norma for v in vetor]


class EmbeddingsOllama:
    def __init__(
        self, cfg: ConfigEmbeddings, cliente: httpx.Client | None = None
    ) -> None:
        self.cfg = cfg
        self.dimensao = cfg.dimensao
        self._cliente = cliente or httpx.Client(
            base_url=cfg.base_url, timeout=cfg.timeout_s
        )

    def embutir_documentos(self, textos: list[str]) -> list[list[float]]:
        preparados = [
            self._com_instrucao(t, self.cfg.instrucao_documento) for t in textos
        ]
        vetores: list[list[float]] = []
        for inicio in range(0, len(preparados), self.cfg.lote):
            vetores.extend(self._chamar(preparados[inicio : inicio + self.cfg.lote]))
        return vetores

    def embutir_consulta(self, texto: str) -> list[float]:
        preparado = self._com_instrucao(texto, self.cfg.instrucao_consulta)
        return self._chamar([preparado])[0]

    @staticmethod
    def _com_instrucao(texto: str, instrucao: str) -> str:
        # Convenção da família Qwen3-Embedding: só a consulta é instruída.
        if not instrucao:
            return texto
        return f"Instruct: {instrucao}\nQuery: {texto}"

    def _chamar(self, textos: list[str]) -> list[list[float]]:
        dados = self._post_com_retentativa(
            "/v1/embeddings", {"model": self.cfg.modelo, "input": textos}
        )
        itens = dados.get("data")
        if not isinstance(itens, list) or len(itens) != len(textos):
            recebidos = len(itens) if isinstance(itens, list) else "resposta malformada"
            raise FalhaEmbeddingException(
                f"esperava {len(textos)} vetores, recebeu {recebidos}"
            )
        vetores: list[list[float]] = []
        # Ordena por `index` — mas o campo tem que existir: sem ele, todos
        # cairiam em 0 e o pareamento texto↔vetor ficaria com a ordem de
        # chegada, corrompendo os vetores em silêncio.
        for item in sorted(itens, key=lambda i: self._indice(i)):
            bruto = item.get("embedding")
            if not isinstance(bruto, list):
                raise FalhaEmbeddingException("item da resposta sem 'embedding'")
            if len(bruto) != self.dimensao:
                raise ConfiguracaoEmbeddingInvalidaException(len(bruto), self.dimensao)
            vetor = [float(v) for v in bruto]
            # Vetor nulo é resposta degenerada do modelo: normalizar daria NaN
            # e o pgvector gravaria lixo em silêncio.
            if not any(vetor):
                raise FalhaEmbeddingException("vetor nulo devolvido pelo modelo")
            vetores.append(normalizar(vetor))
        return vetores

    @staticmethod
    def _indice(item: Any) -> int:
        indice = item.get("index")
        if not isinstance(indice, int):
            raise FalhaEmbeddingException("item da resposta sem 'index'")
        return indice

    def _post_com_retentativa(self, rota: str, corpo: dict[str, Any]) -> dict[str, Any]:
        motivo = "sem resposta"
        for tentativa in range(_TENTATIVAS):
            try:
                resposta = self._cliente.post(rota, json=corpo)
            except httpx.HTTPError as exc:
                motivo = type(exc).__name__
            else:
                if resposta.status_code < 500:
                    if resposta.status_code >= 400:
                        raise FalhaEmbeddingException(f"HTTP {resposta.status_code}")
                    return resposta.json()
                motivo = f"HTTP {resposta.status_code}"
            if tentativa < _TENTATIVAS - 1:
                time.sleep(_BACKOFF_BASE_S * 2**tentativa)
        raise FalhaEmbeddingException(motivo)


class EmbeddingsFake:
    """Duplo determinístico: a suíte nunca toca a rede nem exige Ollama."""

    def __init__(self, dimensao: int | None = None) -> None:
        self.dimensao = dimensao if dimensao is not None else settings.embedding_dim

    def embutir_documentos(self, textos: list[str]) -> list[list[float]]:
        return [self._vetor(t) for t in textos]

    def embutir_consulta(self, texto: str) -> list[float]:
        return self._vetor(texto)

    def _vetor(self, texto: str) -> list[float]:
        semente = hashlib.sha256(texto.strip().lower().encode("utf-8")).digest()
        repetida = semente * (self.dimensao // len(semente) + 1)
        return normalizar([(b - 127.5) / 127.5 for b in repetida[: self.dimensao]])


_embeddings: EmbeddingsOllama | None = None


def get_embeddings() -> Embeddings:
    """Dependência FastAPI, no mesmo padrão de `get_armazenamento`.

    O cliente HTTP é construído uma vez e reusado em todas as requisições:
    criar um por chamada vazaria pool de conexões e descritores de arquivo.
    """
    global _embeddings
    if _embeddings is None:
        _embeddings = EmbeddingsOllama(ConfigEmbeddings.das_settings())
    return _embeddings
