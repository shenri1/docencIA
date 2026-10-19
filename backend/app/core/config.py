import warnings
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SECRET_KEY_DEV_DEFAULT = "dev-secret-key-change-me-in-production-32b"
_PSEUDONIMO_KEY_DEV_DEFAULT = "dev-pseudonimo-key-change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Fail-closed: só "desenvolvimento" explícito permite as chaves default
    # (que estão no repositório). Sem AMBIENTE, vale o mais restritivo.
    ambiente: Literal["desenvolvimento", "producao"] = "producao"

    database_url: str = "postgresql+psycopg://docencia:changeme@localhost:5432/docencia"
    embedding_dim: int = 1024

    secret_key: str = _SECRET_KEY_DEV_DEFAULT
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # --- LGPD ---
    # Separada de secret_key: trocar a chave do JWT não pode mudar todos os
    # pseudônimos do log.
    pseudonimo_key: str = _PSEUDONIMO_KEY_DEV_DEFAULT

    # --- Primeiro administrador ---
    # Lidos só pela migração e1a4c8f02b77, que semeia a conta. Sem os três, ela
    # não cria ninguém: a senha nunca mora no repositório.
    admin_credencial: str | None = None
    admin_nome: str | None = None
    admin_senha: str | None = None

    # --- Materiais ---
    storage_dir: str = "./storage"
    max_upload_mb: int = 30
    ocr_enabled: bool = True
    ocr_langs: str = "por+eng"
    ocr_dpi: int = 300
    ocr_confianca_minima: float = 60.0
    ocr_max_paginas: int = 150
    # Tetos de recurso do pipeline de upload: MAX_UPLOAD_MB só limita o arquivo
    # comprimido/declarado, não o que o parser aloca ao abri-lo.
    max_pdf_paginas: int = 1000
    ocr_max_megapixels: float = 40.0
    max_ooxml_descomprimido_mb: int = 200
    max_ooxml_entradas: int = 10_000
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
    # Qwen3 comum como juiz yes/no, não o Qwen3-Reranker: o GGUF
    # dengcao/Qwen3-Reranker devolve distribuição uniforme pelo /api/generate
    # (medido; ver docstring de services/rag/rerank.py).
    rerank_model: str = "qwen3:1.7b"
    rerank_instrucao: str = (
        "Given a web search query, retrieve relevant passages that answer the query"
    )
    rerank_timeout_s: float = 120.0

    # Rerank custa uma chamada HTTP por par: 20 candidatos, não 40.
    rag_candidatos: int = 20
    rag_top_k: int = 8
    # a busca de cada "articular com". Menos trechos e menos
    # candidatos que a da âncora: até 2 cruzamentos somam 20 chamadas de rerank
    # por questão, e 8 + 2 × 3 = 14 trechos precisam caber no num_ctx.
    rag_top_k_cruzamento: int = 3
    rag_candidatos_cruzamento: int = 10

    chunk_max_chars: int = 1200
    chunk_overlap_chars: int = 200
    chunk_min_chars: int = 300

    # --- Provider Adapter ---
    # Usado quando ProvedorLLM.endpoint é NULL. No Compose vira
    # http://host.docker.internal:11434.
    llm_base_url: str = "http://localhost:11434"
    # Protocolo do servidor em llm_base_url: "ollama" (/api/chat) ou
    # "llama-server" (/v1/chat/completions; serve também o llama-swap). Só vale
    # para a geração: embeddings e rerank seguem no Ollama.
    llm_protocolo: Literal["ollama", "llama-server"] = "ollama"
    # O default do Ollama é 4096 e ele TRUNCA o prompt em silêncio para caber.
    # O prompt do Gerador carrega prompt mestre + 8 trechos do RAG + schema.
    llm_num_ctx: int = 8192
    llm_timeout_s: float = 180.0
    llm_tentativas_por_provedor: int = 2
    # Rotas de LLM são síncronas e seguram uma thread do pool (40 por padrão no
    # anyio) durante toda a geração. Este teto reserva o resto do pool para
    # login, health e leituras. É por processo: N workers do uvicorn => N vezes.
    llm_max_concorrentes: int = 4
    llm_temperatura_padrao: float = 0.3
    llm_max_tokens_padrao: int = 2048

    # --- Geração ---
    # Acima do llm_temperatura_padrao de propósito: com 29 questões sobre o
    # mesmo material, repetição é o risco maior.
    geracao_temperatura: float = 0.4
    geracao_max_tokens: int = 2048

    # --- Crítico ---
    # Abaixo da temperatura do Gerador (0,4): revisar pede conservadorismo. A
    # saída tem o mesmo schema da geração, então o teto de tokens é o mesmo.
    # Baixado de 0,2 para 0,1 em 2026-10-09 (o mesmo mínimo do auditor).
    critico_temperatura: float = 0.1
    critico_max_tokens: int = 2048

    # --- Auditoria ---
    # O mínimo da cadeia, junto com o crítico (0,1): auditar pede o mínimo de
    # invenção. sempre disse 0,1; o código estava 0,2 até 2026-10-09.
    auditoria_temperatura: float = 0.1
    # 1024 cortou a saída no uso. O schema
    # agora limita achados e textos; 2048, o teto da geração, cobre o pior caso.
    auditoria_max_tokens: int = 2048

    @model_validator(mode="after")
    def _recusar_chaves_default_em_producao(self) -> Settings:
        if self.ambiente == "producao":
            usando_default = [
                nome
                for nome, valor, default in (
                    ("SECRET_KEY", self.secret_key, _SECRET_KEY_DEV_DEFAULT),
                    (
                        "PSEUDONIMO_KEY",
                        self.pseudonimo_key,
                        _PSEUDONIMO_KEY_DEV_DEFAULT,
                    ),
                )
                if valor == default
            ]
            if usando_default:
                raise ValueError(
                    f"{', '.join(usando_default)} com o valor default de "
                    "desenvolvimento (público no repositório) em AMBIENTE=producao. "
                    "Defina valores próprios no .env "
                    '(python -c "import secrets; print(secrets.token_hex(32))") '
                    "ou, em máquina de desenvolvimento, AMBIENTE=desenvolvimento."
                )
        return self


settings = Settings()

if settings.secret_key == _SECRET_KEY_DEV_DEFAULT:
    warnings.warn(
        "SECRET_KEY não configurado — usando default de desenvolvimento. "
        "Isso nunca é aceitável em produção: defina SECRET_KEY no .env "
        '(ex.: python -c "import secrets; print(secrets.token_hex(32))").',
        stacklevel=2,
    )

if settings.pseudonimo_key == _PSEUDONIMO_KEY_DEV_DEFAULT:
    warnings.warn(
        "PSEUDONIMO_KEY não configurado — usando default de desenvolvimento. "
        "Em produção, defina PSEUDONIMO_KEY no .env; trocá-la depois torna os "
        "pseudônimos antigos incomparáveis com os novos.",
        stacklevel=2,
    )
