"""Juiz de aderência — Núcleo Semântico.

Juiz fixo, fora da cadeia de provedores: fallback para outro modelo mudaria a
régua no meio da medição. Roda em CPU para não disputar a VRAM com o gerador
Só observa: quem chama decide o que fazer com uma falha.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

from backend.app.core.config import settings
from backend.app.services.provedor.tipos import UsoTokens

# Fora de `app/prompt/` de propósito: tudo lá entra no hash do PromptMestre,
# e mexer na régua do juiz não pode exigir versão nova do prompt de
# geração nem travar a geração com PromptDivergenteException.
_PROMPT = (Path(__file__).parent / "prompt_juiz.md").read_text(encoding="utf-8")
VERSAO_PROMPT_JUIZ = "aderencia@" + hashlib.sha256(_PROMPT.encode()).hexdigest()[:12]


class AvaliacaoAderencia(BaseModel):
    nota_tema: int = Field(ge=1, le=5)
    nota_trecho: int = Field(ge=1, le=5)
    justificativa: str = Field(max_length=300)


@dataclass(frozen=True)
class ResultadoJuiz:
    avaliacao: AvaliacaoAderencia
    uso: UsoTokens
    modelo: str
    versao_prompt: str


class FalhaJuizException(Exception):
    pass


class Juiz(Protocol):
    def avaliar(self, tema: str, questao: str, trechos: list[str]) -> ResultadoJuiz: ...


@dataclass(frozen=True)
class ConfigJuiz:
    base_url: str
    modelo: str
    timeout_s: float
    max_tokens: int

    @classmethod
    def das_settings(cls) -> ConfigJuiz:
        return cls(
            base_url=settings.juiz_base_url,
            modelo=settings.juiz_model,
            timeout_s=settings.juiz_timeout_s,
            max_tokens=settings.juiz_max_tokens,
        )


def _usuario(tema: str, questao: str, trechos: list[str]) -> str:
    numerados = "\n\n".join(f"[{i}] {t}" for i, t in enumerate(trechos, start=1))
    return f"TEMA:\n{tema}\n\nQUESTÃO:\n{questao}\n\nTRECHOS:\n{numerados}"


class JuizOllama:
    def __init__(self, cfg: ConfigJuiz, cliente: httpx.Client | None = None) -> None:
        self.cfg = cfg
        self._cliente = cliente or httpx.Client(
            base_url=cfg.base_url, timeout=cfg.timeout_s
        )

    def avaliar(self, tema: str, questao: str, trechos: list[str]) -> ResultadoJuiz:
        corpo = {
            "model": self.cfg.modelo,
            "messages": [
                {"role": "system", "content": _PROMPT},
                {"role": "user", "content": _usuario(tema, questao, trechos)},
            ],
            "stream": False,
            "think": False,
            "format": AvaliacaoAderencia.model_json_schema(),
            "options": {
                "temperature": 0,
                "num_gpu": 0,
                "num_predict": self.cfg.max_tokens,
            },
        }
        try:
            resposta = self._cliente.post("/api/chat", json=corpo)
        except httpx.HTTPError as exc:
            raise FalhaJuizException(type(exc).__name__) from exc
        if resposta.status_code >= 400:
            raise FalhaJuizException(f"HTTP {resposta.status_code}")
        try:
            dados = resposta.json()
            avaliacao = AvaliacaoAderencia.model_validate_json(
                dados["message"]["content"]
            )
        except (ValueError, KeyError, TypeError, ValidationError) as exc:
            raise FalhaJuizException(
                f"resposta inválida: {type(exc).__name__}"
            ) from exc
        return ResultadoJuiz(
            avaliacao=avaliacao,
            uso=UsoTokens(
                entrada=dados.get("prompt_eval_count", 0),
                saida=dados.get("eval_count", 0),
            ),
            modelo=self.cfg.modelo,
            versao_prompt=VERSAO_PROMPT_JUIZ,
        )


class JuizFake:
    """Notas 5/5 por padrão; com uma exceção, levanta essa exceção. Guarda as
    chamadas para o teste conferir o que o juiz recebeu."""

    def __init__(self, resultado: AvaliacaoAderencia | Exception | None = None) -> None:
        self._resultado = resultado or AvaliacaoAderencia(
            nota_tema=5, nota_trecho=5, justificativa="fake"
        )
        self.chamadas: list[tuple[str, str, list[str]]] = []

    def avaliar(self, tema: str, questao: str, trechos: list[str]) -> ResultadoJuiz:
        self.chamadas.append((tema, questao, trechos))
        if isinstance(self._resultado, Exception):
            raise self._resultado
        return ResultadoJuiz(
            avaliacao=self._resultado,
            uso=UsoTokens(entrada=10, saida=5),
            modelo="juiz-fake",
            versao_prompt=VERSAO_PROMPT_JUIZ,
        )


_juiz: JuizOllama | None = None


def get_juiz() -> Juiz:
    """Dependência FastAPI. Singleton, como `get_reranker`: um cliente HTTP por
    processo."""
    global _juiz
    if _juiz is None:
        _juiz = JuizOllama(ConfigJuiz.das_settings())
    return _juiz
