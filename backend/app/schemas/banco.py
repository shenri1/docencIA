from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain import RegraQualidade


class BancoCriar(BaseModel):
    n_alvo: int = Field(
        ..., ge=1, le=100, description="Quantas questões o banco deve ter."
    )
    versao: str = Field(..., max_length=50, description="Identificador do banco.")


class AncoraImprodutivaResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    numero: int = Field(..., description="Número que a questão teria recebido.")
    localizacao: str = Field(..., description="Onde no material estava a âncora.")
    motivo: str = Field(..., description="O que faltou para sustentar a questão.")


class ViolacaoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    regra: RegraQualidade = Field(..., description="Regra /020b violada.")
    alvo: str = Field(..., description='Letra da alternativa, "enunciado" ou "questao".')
    detalhe: str = Field(..., description="O que foi medido.")


class ItemComViolacaoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    numero: int
    violacoes: list[ViolacaoResposta] = Field(
        ..., description="Violações que sobreviveram à revisão."
    )


class ResumoBancoResposta(BaseModel):
    """A lista de âncoras improdutivas só existe aqui — não é persistida."""

    model_config = ConfigDict(from_attributes=True)

    banco_id: int
    geradas: int = Field(..., description="Questões persistidas nesta chamada.")
    ja_existentes: int = Field(
        ..., description="Questões puladas por já existirem (retomada)."
    )
    improdutivas: list[AncoraImprodutivaResposta] = Field(
        ..., description="Âncoras que não sustentaram questão."
    )
    com_violacoes: list[ItemComViolacaoResposta] = Field(
        ...,
        description="Questões persistidas com violação de forma, para o docente "
        "decidir na janela de exclusões.",
    )
