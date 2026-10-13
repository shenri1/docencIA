"""Formato de entrada e saída das orientações do docente."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from backend.app.domain import EstadoOrientacao, OrigemOrientacao


def _aparar(valor: object) -> object:
    """Texto só de espaços vira ausência: o formulário manda os dois campos."""
    if isinstance(valor, str):
        return valor.strip() or None
    return valor


TextoOrientacao = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


class OrientacaoCriar(BaseModel):
    o_que_mudar: TextoOrientacao = Field(
        ..., description="Orientação de estilo para as próximas gerações da sessão."
    )


class DirecaoVariacao(BaseModel):
    """Corpo opcional da substituição. Os dois textos vão para o
    pedido sem interpretação: `cruzar_com` também vira consulta ao RAG."""

    cruzar_com: Annotated[str | None, BeforeValidator(_aparar)] = Field(
        None, max_length=200, description="Um assunto do material a articular."
    )
    o_que_mudar: Annotated[str | None, BeforeValidator(_aparar)] = Field(
        None, max_length=500, description="O que mudar na questão, em texto livre."
    )
    acumular: bool = Field(
        False, description="Aplicar também às próximas gerações desta sessão."
    )

    @model_validator(mode="after")
    def _algum_texto(self) -> DirecaoVariacao:
        if self.cruzar_com is None and self.o_que_mudar is None:
            raise ValueError("Informe o assunto a articular, o que mudar, ou os dois.")
        return self


class OrientacaoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    origem: OrigemOrientacao
    estado: EstadoOrientacao
    o_que_mudar: str | None
    cruzar_com: str | None
    banco_id: int | None = Field(..., description="Só na origem questao.")
    numero_origem: int | None = Field(..., description="Só na origem questao.")
    criada_em: datetime
