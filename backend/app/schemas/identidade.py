from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain import PerfilDocente


class DocenteCriar(BaseModel):
    nome: str = Field(..., max_length=255, description="Nome completo do docente.")
    credencial_institucional: str = Field(
        ...,
        max_length=255,
        description="Identificador único de login (ex.: matrícula institucional).",
    )
    senha: str = Field(
        ...,
        min_length=8,
        max_length=72,
        description=(
            "Senha em texto puro — usada só pra gerar o hash, nunca persistida. "
            "Limite de 72 bytes (não caracteres) por restrição do bcrypt — "
            "acentos e outros caracteres não-ASCII ocupam mais de 1 byte em UTF-8."
        ),
    )


class DocenteResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Identificador interno do docente.")
    nome: str = Field(..., description="Nome completo do docente.")
    credencial_institucional: str = Field(
        ..., description="Identificador único de login."
    )
    perfil: PerfilDocente = Field(..., description="Nível de acesso do docente.")


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT de acesso.")
    token_type: str = Field(default="bearer", description="Sempre 'bearer'.")
