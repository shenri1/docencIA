import os
import warnings

from pydantic_settings import BaseSettings, SettingsConfigDict

_SECRET_KEY_DEV_DEFAULT = os.environ.get("SECRET_KEY")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://docencia:changeme@localhost:5432/docencia"
    embedding_dim: int = 1536

    secret_key: str = _SECRET_KEY_DEV_DEFAULT
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480


settings = Settings()

if settings.secret_key == _SECRET_KEY_DEV_DEFAULT:
    warnings.warn(
        stacklevel=2,
    )
