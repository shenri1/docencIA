from backend.app.core.config import Settings, settings


def test_settings_tem_campos_de_autenticacao():
    settings = Settings()
    assert isinstance(settings.secret_key, str) and settings.secret_key
    assert settings.algorithm == "HS256"
    assert settings.access_token_expire_minutes == 480


def test_settings_tem_campos_de_materiais():
    settings = Settings()
    assert settings.storage_dir == "./storage"
    assert settings.max_upload_mb == 30
    assert settings.ocr_enabled is True
    assert settings.ocr_langs == "por+eng"
    assert settings.ocr_dpi == 300
    assert settings.ocr_confianca_minima == 60.0
    assert settings.ocr_max_paginas == 150
    assert settings.min_chars_pagina == 25
    assert settings.limiar_paginas_legiveis == 0.8
    assert settings.tesseract_cmd is None


def test_secret_key_default_e_uma_string_literal():
    """Regressão: o default não pode vir de os.environ (viraria None quando
    a variável não está exportada, violando a anotação `str`)."""
    campo = Settings.model_fields["secret_key"]
    assert isinstance(campo.default, str)
    assert campo.default


def test_embedding_dim_e_1024_para_caber_no_indice_hnsw():
    # O teto do índice hnsw do pgvector é 2000 dimensões; 1024 é a saída
    # nativa do qwen3-embedding:0.6b, sem truncagem.
    assert settings.embedding_dim == 1024


def test_defaults_do_rag():
    assert settings.embedding_base_url == "http://localhost:11434"
    assert settings.embedding_model == "dengcao/Qwen3-Embedding-0.6B:Q8_0"
    assert settings.embedding_batch == 64
    assert settings.rerank_model == "dengcao/Qwen3-Reranker-0.6B:Q8_0"
    assert settings.rag_candidatos == 20
    assert settings.rag_top_k == 8
    assert settings.chunk_max_chars == 1200
    assert settings.chunk_overlap_chars == 200
    assert settings.chunk_min_chars == 300


def test_defaults_de_modelo_apontam_para_tags_realmente_instaladas():
    # Regressão: os defaults apontavam para `qwen3-embedding:0.6b`
    # e para a tag `:F16`, que não existem na máquina alvo. Como não há .env
    # no projeto, o default É o valor usado, e a primeira chamada dava 404.
    assert settings.embedding_model == "dengcao/Qwen3-Embedding-0.6B:Q8_0"
    assert settings.rerank_model == "dengcao/Qwen3-Reranker-0.6B:Q8_0"


def test_defaults_do_provider_adapter():
    assert settings.llm_base_url == "http://localhost:11434"
    # 4096 é o default do Ollama e trunca o prompt do Gerador em silêncio.
    assert settings.llm_num_ctx == 8192
    assert settings.llm_timeout_s == 180.0
    assert settings.llm_tentativas_por_provedor == 2
    assert settings.llm_temperatura_padrao == 0.3
    assert settings.llm_max_tokens_padrao == 2048


def test_defaults_da_geracao():
    # Mais alta que llm_temperatura_padrao (0.3): 29 itens idênticos são pior
    # que 29 itens imperfeitos.
    assert settings.geracao_temperatura == 0.4
    # Medido: 920 tokens em k=5, 1172 em k=11 — 57% do teto no pior caso.
    assert settings.geracao_max_tokens == 2048
