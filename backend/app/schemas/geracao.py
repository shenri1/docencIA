"""Schema da SAÍDA do modelo — não confundir com schema de resposta da API.

Construído por K porque a restrição de contagem depende dele. Medido contra o
Ollama: `minItems`/`maxItems` são honrados pela decodificação restrita, então
a estrutura é imposta, não esperada. Sem a restrição, o modelo
entrega 1 invalidação para 4 distratores.
"""

from typing import Literal

from pydantic import BaseModel, Field, create_model

from backend.app.domain import NivelBloom, TipoQuestao

K_MINIMO = 2
K_MAXIMO = 11

# Letra é posição, atribuída pelo código. Com `letra` e `correta` na mão do
# modelo, nada impedia letra duplicada (que quebra a unique constraint no meio
# do laço) nem zero ou duas corretas.
LETRAS = "ABCDEFGHIJK"

# O remove "Criar" da múltipla escolha. Na discursiva ele volta a
# ser operacionalizável, então a restrição vive no schema, não no enum.
BLOOM_OBJETIVA = tuple(n.value for n in NivelBloom if n is not NivelBloom.CRIAR)


class AlternativaGerada(BaseModel):
    texto: str
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


def montar_schema_objetiva(k: int) -> type[BaseModel]:
    """Devolve um modelo com um único campo `resultado`, união discriminada
    entre questão gerada e insuficiência de fonte."""
    if not K_MINIMO <= k <= K_MAXIMO:
        raise ValueError(f"k deve estar entre {K_MINIMO} e {K_MAXIMO}, recebido {k}")

    # cada motivo diz a qual alternativa se refere. Fechada por enum
    # como `letra_correta` — o que a decodificação restrita pode impor não deve
    # ser esperado do modelo. Distintas e diferentes da correta não cabem em
    # JSON Schema: são a regra `invalidacao_letra_invalida` do validador.
    invalidacao = create_model(
        f"InvalidacaoGerada{k}",
        letra=(Literal[tuple(LETRAS[:k])], ...),
        motivo=(str, ...),
    )
    justificativa = create_model(
        f"JustificativaGerada{k}",
        objetivo_cognitivo=(str, ...),
        justificativa_correta=(str, ...),
        # Uma invalidação por distrator: k alternativas, uma correta.
        invalidacao_distratores=(
            list[invalidacao],
            Field(min_length=k - 1, max_length=k - 1),
        ),
        verificacao_unicidade=(bool, ...),
        texto_verificacao_unicidade=(str, ...),
    )
    questao = create_model(
        f"QuestaoGerada{k}",
        tipo=(Literal["questao"], ...),
        enunciado=(str, ...),
        nivel_bloom=(Literal[BLOOM_OBJETIVA], ...),
        tema=(str, ...),
        # a regra de sobreposição temática entre Provas A e B compara
        # subtema. Obrigatório, não opcional: campo opcional em schema de saída
        # restrita é campo que o modelo omite.
        subtema=(str, ...),
        alternativas=(
            list[AlternativaGerada],
            Field(min_length=k, max_length=k),
        ),
        # Enum das k primeiras letras: exatamente uma correta vira restrição
        # da decodificação, como o NivelBloom, em vez de regra a validar.
        letra_correta=(Literal[tuple(LETRAS[:k])], ...),
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


class AspectoGerado(BaseModel):
    """A fonte vive dentro do aspecto: pedir ao modelo um índice para
    outra lista é a referência cruzada que modelo pequeno erra, e assim
    aspecto sem fonte é irrepresentável."""

    texto: str
    fonte: FonteGerada


class QuestaoDiscursivaGerada(BaseModel):
    tipo: Literal["questao_discursiva"]
    enunciado: str
    nivel_bloom: NivelBloom
    tema: str
    subtema: str
    objetivo_cognitivo: str
    aspectos_esperados: list[AspectoGerado] = Field(min_length=2, max_length=5)


class ResultadoGeracaoDiscursiva(BaseModel):
    resultado: QuestaoDiscursivaGerada | InsuficienciaFonte = Field(
        discriminator="tipo"
    )


def montar_schema_discursiva() -> type[BaseModel]:
    """Sem K: a discursiva não tem alternativas. Fixo, mas exposto como função
    para ter a mesma forma de uso que a objetiva."""
    return ResultadoGeracaoDiscursiva


def montar_schema(tipo: TipoQuestao, k: int) -> type[BaseModel]:
    if tipo is TipoQuestao.OBJETIVA:
        return montar_schema_objetiva(k)
    return montar_schema_discursiva()
