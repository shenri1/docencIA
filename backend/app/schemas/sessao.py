from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain import EstadoSessao
from backend.app.schemas.orientacao import TextoOrientacao

# Oito erros típicos distintos para K = 11 é irreal.
MAX_K_COM_CALCULO = 5


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
    p_calculo: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Percentual de objetivas de cálculo numérico.",
    )
    orientacoes: list[TextoOrientacao] = Field(
        default_factory=list,
        max_length=5,
        description="Orientações de estilo para todas as questões da sessão.",
    )

    @model_validator(mode="after")
    def _calculo_exige_k_pequeno(self) -> "SessaoCriar":
        if self.p_calculo > 0 and self.k_alternativas > MAX_K_COM_CALCULO:
            raise ValueError(
                f"questões de cálculo exigem no máximo {MAX_K_COM_CALCULO} "
                f"alternativas (recebido {self.k_alternativas}): sem isso não há "
                f"{self.k_alternativas - 1} erros típicos distintos"
            )
        return self


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
    p_calculo: int = Field(
        ..., description="Percentual de objetivas de cálculo."
    )
    estado: EstadoSessao = Field(..., description="Estado atual da sessão.")
