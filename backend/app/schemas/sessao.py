from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain import EstadoSessao


class SessaoCriar(BaseModel):
    disciplina: str = Field(..., max_length=255, description="Disciplina da avaliação.")
    periodo: str = Field(
        ..., max_length=50, description="Período letivo (ex.: 2026.2)."
    )
    tema_escopo: str | None = Field(
        default=None, max_length=500, description="Recorte temático da avaliação."
    )
    area_do_conhecimento: str | None = Field(
        default=None, max_length=255, description="Área do conhecimento da disciplina."
    )
    k_alternativas: int = Field(
        ..., ge=2, le=11, description="Número de alternativas por questão (letras A–K)."
    )
    p_f: int = Field(..., ge=0, le=100, description="Percentual de questões fáceis.")
    p_m: int = Field(..., ge=0, le=100, description="Percentual de questões médias.")
    p_d: int = Field(..., ge=0, le=100, description="Percentual de questões difíceis.")


class SessaoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Identificador da sessão.")
    disciplina: str
    periodo: str
    tema_escopo: str | None
    area_do_conhecimento: str | None
    k_alternativas: int
    p_f: int
    p_m: int
    p_d: int
    estado: EstadoSessao = Field(..., description="Estado atual da sessão.")
