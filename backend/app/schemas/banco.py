from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain import RegraQualidade, TipoQuestao

# Regra de negócio, não configuração: duas chamadas ao modelo por questão
# (~38 s) fazem 25 questões custarem ~16 minutos síncronos, e 25 ainda
# sustentam Provas A e B com o padrão de 10 questões cada.
N_MAXIMO_BANCO = 25


class BancoCriar(BaseModel):
    n_objetivas: int = Field(..., ge=0, description="Quantas questões objetivas.")
    n_discursivas: int = Field(..., ge=0, description="Quantas questões discursivas.")
    versao: str = Field(..., max_length=50, description="Identificador do banco.")

    @model_validator(mode="after")
    def _soma_dentro_do_limite(self) -> BancoCriar:
        total = self.n_objetivas + self.n_discursivas
        if not 1 <= total <= N_MAXIMO_BANCO:
            raise ValueError(
                f"o banco deve ter de 1 a {N_MAXIMO_BANCO} questões somando os "
                f"dois tipos; pedido: {total}"
            )
        return self


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
    geradas_por_tipo: dict[TipoQuestao, int] = Field(
        ..., description="Questões persistidas nesta chamada, por tipo."
    )
