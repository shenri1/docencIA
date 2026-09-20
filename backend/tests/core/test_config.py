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
    assert settings.embedding_model == "qwen3-embedding:0.6b"
    assert settings.embedding_batch == 64
    assert settings.rerank_model == "dengcao/Qwen3-Reranker-0.6B:F16"
    assert settings.rag_candidatos == 20
    assert settings.rag_top_k == 8
    assert settings.chunk_max_chars == 1200
    assert settings.chunk_overlap_chars == 200
    assert settings.chunk_min_chars == 300
