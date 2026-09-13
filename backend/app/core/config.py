import warnings

from pydantic_settings import BaseSettings, SettingsConfigDict

_SECRET_KEY_DEV_DEFAULT = "dev-secret-key-change-me-in-production-32b"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://docencia:changeme@localhost:5432/docencia"
    embedding_dim: int = 1536

    # trocar via .env em qualquer ambiente real de producao.
    # Sem default aceitável em produção —
    # o valor abaixo só existe pra não quebrar dev/testes; ver aviso emitido
    # logo abaixo quando ele continua em uso.
    secret_key: str = _SECRET_KEY_DEV_DEFAULT
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480


settings = Settings()

if settings.secret_key == _SECRET_KEY_DEV_DEFAULT:
    warnings.warn(
        "SECRET_KEY não configurado — usando default de desenvolvimento. "
        "Isso nunca é aceitável em produção: defina SECRET_KEY no .env "
        '(ex.: python -c "import secrets; print(secrets.token_hex(32))").',
        stacklevel=2,
    )
