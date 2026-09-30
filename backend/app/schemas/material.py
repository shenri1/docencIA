from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain import FormatoArquivo, OrigemTexto, TipoMaterial


class MaterialResposta(BaseModel):
    """Nunca expõe chave de armazenamento, hash ou caminho de servidor."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Identificador do material.")
    identificador_curto: str = Field(
        ..., description="Identificador usado nas citações de fonte (S1, P1, L1…)."
    )
    nome_arquivo: str = Field(..., description="Nome original enviado pelo docente.")
    tipo: TipoMaterial = Field(..., description="Classificação didática do material.")
    formato: FormatoArquivo = Field(..., description="Formato do arquivo enviado.")
    contagem_paginas_logicas: int | None = Field(
        default=None, description="Páginas físicas (PDF) ou slides (PPTX)."
    )
    origem_texto: OrigemTexto = Field(
        ..., description="Se o texto veio da camada nativa, de OCR, ou de ambos."
    )
    tamanho_bytes: int = Field(..., description="Tamanho do arquivo em bytes.")
    criado_em: datetime = Field(..., description="Momento do upload.")


class IndiceResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    materiais: list[MaterialResposta] = Field(
        ..., description="Materiais da sessão, em ordem de envio."
    )
    confirmado: bool = Field(
        ..., description="Se o docente já confirmou o índice."
    )
