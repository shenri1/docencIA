"""Tipos do contrato de geração.

O schema de saída é um modelo Pydantic, não um dict de JSON Schema: Pydantic
já é dependência do projeto e fecha os dois lados — `model_json_schema()`
alimenta o `format` do Ollama e `model_validate_json()` valida a volta.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from backend.app.core.config import settings


@dataclass(frozen=True)
class UsoTokens:
    entrada: int
    saida: int


@dataclass(frozen=True)
class RequisicaoLLM:
    sistema: str
    usuario: str
    formato: type[BaseModel]
    # None = usar o default da configuração. Resolver aqui acoplaria o tipo
    # às settings no momento do import.
    temperatura: float | None = None
    max_tokens: int | None = None


@dataclass(frozen=True)
class RespostaLLM:
    conteudo: BaseModel
    uso: UsoTokens
    # Qual provedor de fato serviu — não o primeiro da cadeia. 
    # precisa registrar com qual modelo cada questão foi gerada.
    provedor_id: int
    modelo: str


@dataclass(frozen=True)
class ConfigLLM:
    base_url: str
    num_ctx: int
    timeout_s: float
    temperatura_padrao: float
    max_tokens_padrao: int

    @classmethod
    def das_settings(cls) -> ConfigLLM:
        return cls(
            base_url=settings.llm_base_url,
            num_ctx=settings.llm_num_ctx,
            timeout_s=settings.llm_timeout_s,
            temperatura_padrao=settings.llm_temperatura_padrao,
            max_tokens_padrao=settings.llm_max_tokens_padrao,
        )
