"""Agente Orquestrador: comandos de vocabulário fechado e respostas."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Body
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain import ComandoOrquestrador, Marco
from backend.app.schemas.banco import (
    N_MAXIMO_BANCO,
    ItemCatalogoResposta,
    RelatorioImpactoResposta,
    ResumoAuditoriaResposta,
    ResumoBancoResposta,
)
from backend.app.schemas.exportacao import ExportacaoResposta
from backend.app.schemas.material import IndiceResposta
from backend.app.schemas.prova import GabaritoResposta, ProvasMontadasResposta


class ComandoProsseguir(BaseModel):
    """Executa o passo do marco atual. Os campos exigidos dependem do marco —
    `GET /sessoes/{id}/marco` os lista em `campos_prosseguir`."""

    comando: Literal["prosseguir"]
    versao: str | None = Field(
        default=None, max_length=50, description="Banco alvo; nova no M2."
    )
    revisao_esperada: int | None = Field(
        default=None, ge=0, description="Revisão do banco que o docente viu."
    )
    n_objetivas: int | None = Field(default=None, ge=0)
    n_discursivas: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _contagens_juntas_e_no_limite(self) -> ComandoProsseguir:
        contagens = (self.n_objetivas, self.n_discursivas)
        if contagens == (None, None):
            return self
        if None in contagens:
            raise ValueError("n_objetivas e n_discursivas vêm juntos")
        total = self.n_objetivas + self.n_discursivas
        if not 1 <= total <= N_MAXIMO_BANCO:
            raise ValueError(
                f"a soma dos dois tipos vai de 1 a {N_MAXIMO_BANCO}; pedido: {total}"
            )
        return self


class ComandoExcluir(BaseModel):
    comando: Literal["excluir"]
    versao: str = Field(..., max_length=50)
    revisao_esperada: int = Field(..., ge=0)
    numeros: list[int] = Field(..., min_length=1, max_length=N_MAXIMO_BANCO)


class ComandoAuditar(BaseModel):
    """Sem `revisao_esperada`: auditar não muda o banco."""

    comando: Literal["auditar"]
    versao: str = Field(..., max_length=50)


Comando = Annotated[
    ComandoProsseguir | ComandoExcluir | ComandoAuditar,
    Body(discriminator="comando"),
]


class MarcoBancoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    versao: str
    banco_id: int
    revisao: int
    marco: Marco
    motivo: str | None = Field(..., description="Só em bloqueado: por quê.")
    n_alvo: int
    n_atual: int
    lacunas: int = Field(
        ...,
        description="Números do plano sem questão (insuficiência de fonte). "
        "Reenviar POST /sessoes/{id}/banco retenta só eles.",
    )
    alerta_desvio: bool = Field(
        ..., description="Desvio de pF/pM/pD acima de 5 pontos nas ativas."
    )
    objetivas_ativas: int
    objetivas_auditadas: int = Field(..., description="Auditadas NESTA revisão.")
    comandos: list[ComandoOrquestrador]
    campos_prosseguir: list[str]


class MarcoSessaoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sessao_id: int
    marco: Marco
    n_materiais: int
    comandos: list[ComandoOrquestrador]
    campos_prosseguir: list[str]
    bancos: list[MarcoBancoResposta]


class ResultadoComandoResposta(BaseModel):
    """Um campo de resultado preenchido por passo; o cliente sabe qual ler por
    `comando` e `marco_executado`."""

    model_config = ConfigDict(from_attributes=True)

    comando: ComandoOrquestrador
    marco_executado: Marco
    marco: MarcoSessaoResposta
    indice: IndiceResposta | None = None
    banco: ResumoBancoResposta | None = None
    relatorio: RelatorioImpactoResposta | None = None
    catalogo: list[ItemCatalogoResposta] | None = None
    provas: ProvasMontadasResposta | None = None
    gabaritos: list[GabaritoResposta] | None = None
    exportacoes: list[ExportacaoResposta] | None = None
    auditoria: ResumoAuditoriaResposta | None = None
