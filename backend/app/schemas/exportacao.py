from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain import TipoExportacao


class ExportacaoResposta(BaseModel):
    """Sem `caminho_arquivo`, de propósito: a chave de armazenamento nunca sai
    na resposta."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: TipoExportacao
    revisao_banco: int = Field(
        ..., description="Revisão do banco que o arquivo representa."
    )
    hash_conteudo: str = Field(
        ..., description="sha256 do arquivo entregue. Conferível com `sha256sum`."
    )
    criado_em: datetime
