from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RegistroAuditoriaResposta(BaseModel):
    """`ator` é o pseudônimo HMAC do docente, nunca a
    identidade."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo_evento: str
    entidade_afetada: str
    ator: str | None = Field(..., description="Pseudônimo do docente, ou nulo.")
    payload: dict
    timestamp: datetime
