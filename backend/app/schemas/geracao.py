"""Schema da SAÍDA do modelo — não confundir com schema de resposta da API.

Construído por K porque a restrição de contagem depende dele. Medido contra o
Ollama: `minItems`/`maxItems` são honrados pela decodificação restrita, então
a estrutura é imposta, não esperada. Sem a restrição, o modelo
entrega 1 invalidação para 4 distratores.
"""

from typing import Literal

from pydantic import BaseModel, Field, create_model

from backend.app.domain import NivelBloom

_K_MINIMO = 2
_K_MAXIMO = 11


class AlternativaGerada(BaseModel):
    letra: str
    texto: str
    correta: bool
    # distrator que espelha a estrutura da correta.
    e_gemeo_malvado: bool


class FonteGerada(BaseModel):
    # Texto ("P1"), resolvido pelo código contra os trechos enviados. O modelo
    # não tem acesso a id de banco, e não deveria ter.
    identificador_material: str
    localizacao: str
    trecho_base: str


class InsuficienciaFonte(BaseModel):
    """É resultado, não exceção: no laço do banco, recusar-se a
    inventar é comportamento correto."""

    tipo: Literal["insuficiencia_de_fonte"]
    informacao_faltante: str


def montar_schema_questao(k: int) -> type[BaseModel]:
    """Devolve um modelo com um único campo `resultado`, união discriminada
    entre questão gerada e insuficiência de fonte."""
    if not _K_MINIMO <= k <= _K_MAXIMO:
        raise ValueError(f"k deve estar entre {_K_MINIMO} e {_K_MAXIMO}, recebido {k}")

    justificativa = create_model(
        f"JustificativaGerada{k}",
        objetivo_cognitivo=(str, ...),
        justificativa_correta=(str, ...),
        # Uma invalidação por distrator: k alternativas, uma correta.
        invalidacao_distratores=(
            list[str],
            Field(min_length=k - 1, max_length=k - 1),
        ),
        verificacao_unicidade=(bool, ...),
        texto_verificacao_unicidade=(str, ...),
    )
    questao = create_model(
        f"QuestaoGerada{k}",
        tipo=(Literal["questao"], ...),
        enunciado=(str, ...),
        nivel_bloom=(NivelBloom, ...),
        tema=(str, ...),
        alternativas=(
            list[AlternativaGerada],
            Field(min_length=k, max_length=k),
        ),
        fontes=(list[FonteGerada], Field(min_length=1)),
        justificativa=(justificativa, ...),
    )
    return create_model(
        f"ResultadoGeracaoLLM{k}",
        resultado=(
            questao | InsuficienciaFonte,
            Field(discriminator="tipo"),
        ),
    )
