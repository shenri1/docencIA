from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://docencia:changeme@localhost:5432/docencia"
    embedding_dim: int = 1536


settings = Settings()
