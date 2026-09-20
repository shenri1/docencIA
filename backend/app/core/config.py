import warnings

from pydantic_settings import BaseSettings, SettingsConfigDict

_SECRET_KEY_DEV_DEFAULT = "dev-secret-key-change-me-in-production-32b"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://docencia:changeme@localhost:5432/docencia"
    embedding_dim: int = 1536

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


settings = Settings()

if settings.secret_key == _SECRET_KEY_DEV_DEFAULT:
    warnings.warn(
        "SECRET_KEY não configurado — usando default de desenvolvimento. "
        "Isso nunca é aceitável em produção: defina SECRET_KEY no .env "
        '(ex.: python -c "import secrets; print(secrets.token_hex(32))").',
        stacklevel=2,
    )
