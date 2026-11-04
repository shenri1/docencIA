from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain import EstadoProva, FaixaDificuldade, TipoGabarito, TipoQuestao
from backend.app.schemas.banco import N_MAXIMO_BANCO


class ProvasCriar(BaseModel):
    """O docente marca, questão a questão, o que vai para cada prova. A mesma
    questão pode ir para as duas."""

    numeros_a: list[int] = Field(
        ...,
        min_length=1,
        max_length=N_MAXIMO_BANCO,
        description="Números do banco na Prova A.",
    )
    numeros_b: list[int] = Field(
        ...,
        min_length=1,
        max_length=N_MAXIMO_BANCO,
        description="Números do banco na Prova B.",
    )
    revisao_esperada: int = Field(
        ..., ge=0, description="Revisão do banco que o docente estava vendo."
    )

    @model_validator(mode="after")
    def _sem_repeticao(self) -> ProvasCriar:
        for versao, numeros in (("A", self.numeros_a), ("B", self.numeros_b)):
            if len(set(numeros)) != len(numeros):
                raise ValueError(f"a Prova {versao} repete questão")
        return self


class SugestaoProvasResposta(BaseModel):
    """A seleção automática por tipo e faixa, para o docente partir dela."""

    numeros_a: list[int]
    numeros_b: list[int]


class VerificacaoResposta(BaseModel):
    """As duas auditorias pós-montagem. `violacoes` vazia é o
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
        "fica cega para elas — banco gerado antes de existir subtema.",
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
        "exportação é a própria exportação; aqui é aviso.",
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
        "antigo ou o vínculo gravado é inválido.",
    )
    motivo: str


class AspectoGabaritoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ordem: int
    texto: str
    fonte: FonteGabaritoResposta
    item: int | None = Field(
        None, description="Item (1, 2 ou 3) na discursiva com itens."
    )


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
    completo: bool = Field(..., description="Gabarito para 100% das questões da prova.")
    problemas: list[str]
    itens: list[ItemGabaritoResposta]
