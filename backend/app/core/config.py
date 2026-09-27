import warnings

from pydantic_settings import BaseSettings, SettingsConfigDict

_SECRET_KEY_DEV_DEFAULT = "dev-secret-key-change-me-in-production-32b"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://docencia:changeme@localhost:5432/docencia"
    embedding_dim: int = 1024

    secret_key: str = _SECRET_KEY_DEV_DEFAULT
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # --- Materiais ---
    storage_dir: str = "./storage"
    max_upload_mb: int = 30
    ocr_enabled: bool = True
    ocr_langs: str = "por+eng"
    ocr_dpi: int = 300
    ocr_confianca_minima: float = 60.0
    ocr_max_paginas: int = 150
    min_chars_pagina: int = 25
    limiar_paginas_legiveis: float = 0.8
    tesseract_cmd: str | None = None

    # --- RAG ---
    # Ollama roda no host; dentro do Compose a URL vira host.docker.internal.
    embedding_base_url: str = "http://localhost:11434"
    embedding_model: str = "dengcao/Qwen3-Embedding-0.6B:Q8_0"
    # A família Qwen3-Embedding instrui apenas o lado da consulta.
    embedding_instrucao_consulta: str = (
        "Given a web search query, retrieve relevant passages that answer the query"
    )
    embedding_instrucao_documento: str = ""
    embedding_batch: int = 64
    embedding_timeout_s: float = 120.0

    rerank_base_url: str = "http://localhost:11434"
    rerank_model: str = "dengcao/Qwen3-Reranker-0.6B:Q8_0"
    rerank_instrucao: str = (
        "Given a web search query, retrieve relevant passages that answer the query"
    )
    rerank_timeout_s: float = 120.0

    # Rerank custa uma chamada HTTP por par: 20 candidatos, não 40.
    rag_candidatos: int = 20
    rag_top_k: int = 8

    chunk_max_chars: int = 1200
    chunk_overlap_chars: int = 200
    chunk_min_chars: int = 300

    # --- Provider Adapter ---
    # Usado quando ProvedorLLM.endpoint é NULL. No Compose vira
    # http://host.docker.internal:11434.
    llm_base_url: str = "http://localhost:11434"
    # O default do Ollama é 4096 e ele TRUNCA o prompt em silêncio para caber.
    # O prompt do Gerador carrega prompt mestre + 8 trechos do RAG + schema.
    llm_num_ctx: int = 8192
    llm_timeout_s: float = 180.0
    llm_tentativas_por_provedor: int = 2
    llm_temperatura_padrao: float = 0.3
    llm_max_tokens_padrao: int = 2048

    # --- Geração ---
    # Acima do llm_temperatura_padrao de propósito: com 29 questões sobre o
    # mesmo material, repetição é o risco maior.
    geracao_temperatura: float = 0.4
    geracao_max_tokens: int = 2048

    # --- Crítico ---
    # Abaixo da temperatura do Gerador: revisar pede conservadorismo. A saída
    # tem o mesmo schema da geração, então o teto de tokens é o mesmo.
    critico_temperatura: float = 0.2
    critico_max_tokens: int = 2048

    # --- Auditoria ---
    # Abaixo da temperatura do crítico (0,2): auditar pede o mínimo de invenção.
    # Palpite, como o 0,4 do Gerador e o 0,2 do crítico.
    auditoria_temperatura: float = 0.1
    # A saída é uma lista curta de achados, não uma questão inteira.
    auditoria_max_tokens: int = 1024


settings = Settings()

if settings.secret_key == _SECRET_KEY_DEV_DEFAULT:
    warnings.warn(
        "SECRET_KEY não configurado — usando default de desenvolvimento. "
        "Isso nunca é aceitável em produção: defina SECRET_KEY no .env "
        '(ex.: python -c "import secrets; print(secrets.token_hex(32))").',
        stacklevel=2,
    )
