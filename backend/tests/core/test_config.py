import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings, settings


def test_settings_tem_campos_de_autenticacao():
    settings = Settings()
    assert isinstance(settings.secret_key, str) and settings.secret_key
    assert settings.algorithm == "HS256"
    assert settings.access_token_expire_minutes == 480


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
    assert settings.rerank_model == "qwen3:1.7b"
    assert settings.rag_candidatos == 20
    assert settings.rag_top_k == 8


def test_defaults_de_modelo_apontam_para_tags_realmente_instaladas():
    # Regressão: os defaults apontavam para `qwen3-embedding:0.6b`
    # e para a tag `:F16`, que não existem na máquina alvo. Como não há .env
    # no projeto, o default É o valor usado, e a primeira chamada dava 404.
    assert settings.embedding_model == "dengcao/Qwen3-Embedding-0.6B:Q8_0"
    assert settings.rerank_model == "qwen3:1.7b"


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


def test_defaults_do_critico():
    # Revisar pede conservadorismo, não variedade: abaixo dos 0.4 do Gerador.
    assert settings.critico_temperatura == 0.1
    # A saída tem o mesmo schema da geração: mesmo teto.
    assert settings.critico_max_tokens == 2048


# --- Achado 4: chaves de desenvolvimento não podem subir em produção ---

_CHAVE_FORTE = "a" * 64
_OUTRA_CHAVE_FORTE = "b" * 64


@pytest.fixture
def sem_chaves_no_ambiente(monkeypatch):
    for nome in ("SECRET_KEY", "PSEUDONIMO_KEY", "AMBIENTE"):
        monkeypatch.delenv(nome, raising=False)


def test_producao_e_o_ambiente_padrao(sem_chaves_no_ambiente):
    cfg = Settings(
        _env_file=None, secret_key=_CHAVE_FORTE, pseudonimo_key=_OUTRA_CHAVE_FORTE
    )
    assert cfg.ambiente == "producao"


def test_producao_recusa_secret_key_de_desenvolvimento(sem_chaves_no_ambiente):
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(_env_file=None, pseudonimo_key=_OUTRA_CHAVE_FORTE)


def test_producao_recusa_pseudonimo_key_de_desenvolvimento(sem_chaves_no_ambiente):
    with pytest.raises(ValidationError, match="PSEUDONIMO_KEY"):
        Settings(_env_file=None, secret_key=_CHAVE_FORTE)


def test_producao_aceita_chaves_proprias(sem_chaves_no_ambiente):
    cfg = Settings(
        _env_file=None, secret_key=_CHAVE_FORTE, pseudonimo_key=_OUTRA_CHAVE_FORTE
    )
    assert cfg.secret_key == _CHAVE_FORTE


def test_desenvolvimento_aceita_chaves_default(sem_chaves_no_ambiente):
    cfg = Settings(_env_file=None, ambiente="desenvolvimento")
    assert cfg.secret_key and cfg.pseudonimo_key


def test_ambiente_desconhecido_e_recusado(sem_chaves_no_ambiente):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ambiente="staging")
