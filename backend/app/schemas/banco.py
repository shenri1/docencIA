from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain import (
    EstadoBanco,
    EstadoQuestao,
    EventoBanco,
    FaixaDificuldade,
    FormatoItem,
    NivelBloom,
    RegraQualidade,
    RiscoAuditoria,
    TipoQuestao,
)

# Regra de negócio, não configuração: duas chamadas ao modelo por questão
# (~38 s) fazem 25 questões custarem ~16 minutos síncronos, e 25 ainda
# sustentam Provas A e B com o padrão de 10 questões cada.
N_MAXIMO_BANCO = 25


class BancoCriar(BaseModel):
    n_objetivas: int = Field(..., ge=0, description="Quantas questões objetivas.")
    n_discursivas: int = Field(..., ge=0, description="Quantas questões discursivas.")
    versao: str = Field(..., max_length=50, description="Identificador do banco.")
    # o cliente gera em lotes curtos para nenhuma
    # requisição passar do timeout do navegador ou do proxy.
    apos: int = Field(
        0, ge=0, description="Só números do plano maiores que este."
    )
    limite: int | None = Field(
        None,
        ge=1,
        le=N_MAXIMO_BANCO,
        description="Tenta no máximo este tanto de números e devolve. "
        "Sem limite, tenta todos.",
    )

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
    revisao: int = Field(
        ..., description="Revisão do banco — é o que os comandos de controle exigem."
    )
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
    ultimo_numero: int | None = Field(
        ..., description="Último número tentado nesta chamada; nulo se nenhum."
    )
    restantes: int = Field(
        ...,
        description="Números do plano acima do último tentado (ou de `apos`) "
        "ainda sem questão. O laço do cliente termina em zero.",
    )


# --- Controle do Banco ---


class ExclusaoCriar(BaseModel):
    numeros: list[int] = Field(
        ...,
        min_length=1,
        max_length=N_MAXIMO_BANCO,
        description="Números das questões a excluir.",
    )
    revisao_esperada: int = Field(
        ...,
        ge=0,
        description="Revisão que o docente estava vendo. Se o banco mudou, o "
        "comando é recusado com 409.",
    )


class ComandoRevisao(BaseModel):
    revisao_esperada: int = Field(..., ge=0, description="Revisão que o docente viu.")


class RelatorioImpactoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    revisao: int
    evento: EventoBanco
    n_final: int
    contagem_por_faixa: dict[str, dict[str, int]] = Field(
        ..., description="Questões ativas por tipo e faixa."
    )
    desvio_observado: dict[str, dict[str, str | None]] = Field(
        ...,
        description="Desvio em relação ao pF/pM/pD PEDIDO, em pontos percentuais, "
        "por tipo e faixa. Texto, porque Decimal não serializa e float não é "
        "exato. null quando o tipo não tem questão ativa.",
    )
    alerta_desvio: bool = Field(
        ...,
        description="Alguma faixa passou de 5 pontos de desvio em relação ao "
        "pedido. É observação, nunca ação — o docente decide.",
    )
    timestamp: datetime


class FonteResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    identificador_material: str
    localizacao: str
    trecho_base: str


class AlternativaResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    letra: str
    texto: str


class AspectoEsperadoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ordem: int
    texto: str
    fonte: FonteResposta
    item: int | None = Field(
        None,
        description="Item (1, 2 ou 3) na discursiva com itens; null sem itens.",
    )


class QuestaoResposta(BaseModel):
    """Sem justificativa e sem rascunho, de propósito: eles nunca
    aparecem no corpo da questão."""

    model_config = ConfigDict(from_attributes=True)

    numero: int
    tipo: TipoQuestao
    estado: EstadoQuestao
    faixa_dificuldade: FaixaDificuldade
    nivel_bloom: NivelBloom
    tema: str | None
    enunciado: str
    fontes: list[FonteResposta] = Field(..., description="Rastreabilidade.")
    violacoes: list[ViolacaoResposta] = Field(
        ..., description="Violações que sobreviveram à revisão."
    )
    alternativas: list[AlternativaResposta] = Field(
        ..., description="Vazio na discursiva."
    )
    letra_correta: str | None = Field(
        ..., description="Só com com_gabarito=true."
    )
    aspectos_esperados: list[AspectoEsperadoResposta] = Field(
        ..., description="Só com com_gabarito=true — é o gabarito da discursiva."
    )
    formato: FormatoItem = Field(
        ..., description="Formato de item. A discursiva grava proposicao."
    )


class BancoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    banco_id: int
    versao: str
    revisao: int
    rotulo: str = Field(..., description='Versão e revisão juntas, ex.: "v1.r3".')
    estado: EstadoBanco
    n_alvo: int
    n_alvo_objetivas: int
    n_alvo_discursivas: int
    n_atual: int = Field(..., description="Questões ATIVA.")
    ultimo_relatorio: RelatorioImpactoResposta | None
    questoes: list[QuestaoResposta]


class PropostaSubstituicaoResposta(BaseModel):
    """A candidata vem COM gabarito: o docente precisa dele para julgar. Vem sem
    justificativa, pelo mesmo motivo da leitura."""

    numero: int
    candidata: QuestaoResposta | None = None
    motivo_insuficiencia: str | None = Field(
        None, description="o material não sustentou outra questão."
    )
    localizacao: str | None = None


class RejeicaoResposta(BaseModel):
    numero: int
    decisao: str = "rejeitada"


# --- Auditoria sob comando ---


class AchadoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    risco: RiscoAuditoria
    alvo: str = Field(..., description="Letra da alternativa apontada.")
    localizacao: str | None = Field(
        ..., description="Onde no material. Nulo nos achados de forma."
    )
    trecho_fonte: str | None = Field(
        ...,
        description="Trecho que sustenta a concorrência. Nulo nos "
        "achados de forma: assimetria não é concorrência de fonte.",
    )
    proposta_ajuste: str = Field(
        ..., description="Orientação ao docente. Nunca executada."
    )


class QuestaoAuditadaResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    numero: int
    achados: list[AchadoResposta]


class ResumoAuditoriaResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    banco_id: int
    revisao_auditada: int = Field(
        ..., description="Revisão do banco a que estes achados se referem."
    )
    auditadas: int = Field(
        ..., description="Objetivas ativas com registro nesta revisão."
    )
    ja_auditadas: int = Field(
        ..., description="Quantas dessas já tinham registro antes desta chamada."
    )
    discursivas_ignoradas: int = Field(
        ...,
        description="As três verificações são sobre alternativas, e "
        "discursiva não tem nenhuma.",
    )
    questoes: list[QuestaoAuditadaResposta] = Field(
        ..., description="Só as questões com achado."
    )
    proporcao_com_achado: Decimal = Field(
        ...,
        description="Percentual de questões auditadas com ao menos um achado. "
        "É observação, nunca ação — o docente decide se para.",
    )
    sem_verificacao_de_forma: int = Field(
        ...,
        description="Questões de afirmativas ou asserção-razão: as alternativas são "
        "montadas pelo sistema, e a assimetria de forma não se aplica.",
    )


class ItemCatalogoResposta(BaseModel):
    """número do item, tema principal e grau de dificuldade."""

    model_config = ConfigDict(from_attributes=True)

    numero: int
    tipo: TipoQuestao
    tema: str | None = Field(
        ..., description="Tema principal. None se o Gerador não classificou."
    )
    faixa: FaixaDificuldade
