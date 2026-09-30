from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain import EstadoProva, FaixaDificuldade, TipoGabarito, TipoQuestao
from backend.app.schemas.banco import N_MAXIMO_BANCO


class ProvasCriar(BaseModel):
    n_objetivas: int = Field(..., ge=0, description="Objetivas por prova.")
    n_discursivas: int = Field(..., ge=0, description="Discursivas por prova.")
    revisao_esperada: int = Field(
        ..., ge=0, description="Revisão do banco que o docente estava vendo."
    )

    @model_validator(mode="after")
    def _soma_dentro_do_limite(self) -> ProvasCriar:
        total = self.n_objetivas + self.n_discursivas
        if not 1 <= total <= N_MAXIMO_BANCO:
            raise ValueError(
                f"a prova deve ter de 1 a {N_MAXIMO_BANCO} questões somando os "
                f"dois tipos; pedido: {total}"
            )
        return self


class VerificacaoResposta(BaseModel):
    """as duas auditorias pós-montagem. `violacoes` vazia é o
    resultado esperado."""

    model_config = ConfigDict(from_attributes=True)

    violacoes: list[str]
    colisoes_letras: int
    posicoes_objetivas: int
    compartilhadas: int
    subtemas_compartilhados: dict[str, int]


class ProvasMontadasResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    prova_a_id: int
    prova_b_id: int
    revisao_banco: int
    compartilhadas: list[int] = Field(
        ..., description="Números das questões presentes nas duas provas."
    )
    sem_subtema: int = Field(
        ...,
        description="Questões selecionadas sem subtema. A regra de sobreposição "
        "fica cega para elas — banco gerado antes.",
    )
    verificacao: VerificacaoResposta


class AlternativaProvaResposta(BaseModel):
    """Sem `correta`, de propósito."""

    model_config = ConfigDict(from_attributes=True)

    letra: str = Field(..., description="Letra na prova, não a original.")
    texto: str


class ItemProvaResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    posicao: int
    numero: int = Field(..., description="Número da questão no banco.")
    tipo: TipoQuestao
    faixa_dificuldade: FaixaDificuldade
    enunciado: str
    alternativas: list[AlternativaProvaResposta] = Field(
        ..., description="Vazia na discursiva."
    )


class ProvaResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    prova_id: int
    versao: str
    estado: EstadoProva
    n_questoes: int
    n_objetivas: int
    n_discursivas: int
    revisao_banco: int
    banco_revisao_atual: int
    desatualizada: bool = Field(
        ...,
        description="A revisão do banco mudou desde a montagem. Quem bloqueia a "
        "exportação é; aqui é aviso.",
    )
    itens: list[ItemProvaResposta]


# --- Gabarito ---


class FonteGabaritoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    identificador_material: str
    localizacao: str
    trecho_base: str | None = Field(..., description="Só no comentado.")


class InvalidacaoGabaritoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    letra: str | None = Field(
        ...,
        description="Letra DA PROVA da alternativa errada. Nula quando o banco é "
        "anterior à ou o vínculo gravado é inválido.",
    )
    motivo: str


class AspectoGabaritoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ordem: int
    texto: str
    fonte: FonteGabaritoResposta


class ItemGabaritoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    posicao: int
    numero: int
    tipo: TipoQuestao
    letra: str | None = Field(..., description="Letra da correta NA PROVA.")
    fontes: list[FonteGabaritoResposta]
    aspectos: list[AspectoGabaritoResposta] = Field(
        ..., description="Discursiva: o gabarito são os aspectos esperados."
    )
    justificativa_correta: str | None
    invalidacoes: list[InvalidacaoGabaritoResposta]
    objetivo_cognitivo: str | None
    invalidacoes_sem_letra: bool = Field(
        ..., description="Motivos das erradas mostrados sem dizer qual é de qual."
    )
    cita_letra: bool = Field(
        ...,
        description="O texto aprovado cita letra de alternativa, que muda na "
        "prova. Mostrado como está.",
    )


class GabaritoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    prova_id: int
    versao: str
    modalidade: TipoGabarito
    revisao_banco: int = Field(..., description='O "Gabarito_vZ".')
    desatualizada: bool
    completo: bool = Field(
        ..., description="Gabarito para 100% das questões da prova."
    )
    problemas: list[str]
    itens: list[ItemGabaritoResposta]
