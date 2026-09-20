from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PromptCriar(BaseModel):
    """Os parâmetros viajam no corpo porque o texto montado é gravado junto da
    versão: a mesma versão com parâmetros diferentes produziria conteúdo
    diferente, e o registro precisa dizer qual foi."""

    versao: str = Field(..., max_length=50, description="Identificador da versão.")
    papel_definido: str = Field(
        ..., max_length=255, description="Resumo da identidade assumida pelo modelo."
    )
    disciplina: str = Field(..., max_length=255)
    periodo: str = Field(..., max_length=50)
    area_do_conhecimento: str | None = Field(default=None, max_length=255)
    tema_escopo: str | None = Field(default=None, max_length=500)
    k_alternativas: int = Field(..., ge=2, le=11)
    n_faceis: int = Field(..., ge=0)
    n_medias: int = Field(..., ge=0)
    n_dificeis: int = Field(..., ge=0)


class PromptResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    versao: str = Field(..., description="Identificador da versão.")
    papel_definido: str
    conteudo: str = Field(
        ..., description="Texto exato enviado ao modelo nesta versão."
    )
    hash_modulos: str = Field(
        ..., description="SHA-256 dos módulos em disco quando a versão nasceu."
    )
    ativo: bool
    criado_em: datetime
