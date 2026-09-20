from pydantic import BaseModel, ConfigDict, Field


class TrechoResposta(BaseModel):
    """Projeção de `TrechoRecuperado`. Carrega tudo que / exige
    para citar a fonte, e nada de chave de armazenamento."""

    model_config = ConfigDict(from_attributes=True)

    material_id: int = Field(..., description="Identificador do material de origem.")
    identificador_curto: str = Field(
        ..., description="Identificador usado nas citações de fonte (S1, P1, L1…)."
    )
    localizacao: str = Field(
        ..., description="Onde o trecho está no material (página, slide, parágrafo)."
    )
    texto: str = Field(..., description="Trecho-base recuperado.")
    score: float = Field(
        ..., description="Relevância atribuída pelo reordenador (0 a 1)."
    )
    score_vetorial: float = Field(
        ..., description="Similaridade de cosseno antes da reordenação."
    )
