"""Schema da SAÍDA do modelo — não confundir com schema de resposta da API.

Construído por K porque a restrição de contagem depende dele. Medido contra o
Ollama: `minItems`/`maxItems` são honrados pela decodificação restrita, então
a estrutura é imposta, não esperada. Sem a restrição, o modelo
entrega 1 invalidação para 4 distratores.
"""

from typing import Literal

from pydantic import BaseModel, Field, create_model

from backend.app.domain import FormatoItem, NivelBloom, TipoQuestao

K_MINIMO = 2
K_MAXIMO = 11


def n_afirmativas(k: int) -> int:
    """3 afirmativas dão 7 combinações não vazias; acima de K = 7, 4 dão 15."""
    return 3 if k <= 7 else 4


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


CAMPOS_AFIRMATIVA = ("afirmativa_i", "afirmativa_ii", "afirmativa_iii", "afirmativa_iv")


def _validar_k(k: int) -> None:
    if not K_MINIMO <= k <= K_MAXIMO:
        raise ValueError(f"k deve estar entre {K_MINIMO} e {K_MAXIMO}, recebido {k}")


def _resultado(nome: str, questao: type[BaseModel]) -> type[BaseModel]:
    return create_model(
        nome, resultado=(questao | InsuficienciaFonte, Field(discriminator="tipo"))
    )


def montar_schema_objetiva(k: int) -> type[BaseModel]:
    """Devolve um modelo com um único campo `resultado`, união discriminada
    entre questão gerada e insuficiência de fonte."""
    _validar_k(k)

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
        # Contexto primeiro: com decodificação restrita, o modelo escreve o
        # cenário antes da pergunta. Obrigatório e possivelmente vazio
        # na fácil — campo opcional em saída restrita é campo que o modelo omite.
        contexto=(str, ...),
        comando=(str, ...),
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


def montar_schema_afirmativas(
    k: int, configuracao: tuple[bool, ...]
) -> type[BaseModel]:
    """Campos nomeados, não lista: fixar o valor por posição numa lista
    exigiria `prefixItems`, que não foi medido no Ollama. `verdadeira` vem
    antes do texto: o modelo escreve a afirmativa já sabendo o que ela deve ser."""
    _validar_k(k)
    if len(configuracao) != n_afirmativas(k):
        raise ValueError(
            f"K={k} pede {n_afirmativas(k)} afirmativas, configuração tem {len(configuracao)}"
        )
    rotulo = "".join("V" if v else "F" for v in configuracao)
    afirmativas = {
        nome: (
            create_model(
                f"Afirmativa{nome[11:].upper()}{rotulo}",
                verdadeira=(Literal[valor], ...),
                texto=(str, ...),
                justificativa=(str, ...),
            ),
            ...,
        )
        for nome, valor in zip(CAMPOS_AFIRMATIVA, configuracao, strict=False)
    }
    questao = create_model(
        f"QuestaoAfirmativas{rotulo}",
        tipo=(Literal["questao"], ...),
        contexto=(str, ...),
        comando=(str, ...),
        **afirmativas,
        nivel_bloom=(Literal[BLOOM_OBJETIVA], ...),
        tema=(str, ...),
        subtema=(str, ...),
        objetivo_cognitivo=(str, ...),
        fontes=(list[FonteGerada], Field(min_length=1)),
    )
    return _resultado(f"ResultadoAfirmativas{rotulo}", questao)


def montar_schema_assercao_razao() -> type[BaseModel]:
    """O comando e as alternativas são texto fixo do sistema. A configuração
    vai no pedido: verdadeiro ou falso de uma proposição não é campo da saída."""
    questao = create_model(
        "QuestaoAssercaoRazao",
        tipo=(Literal["questao"], ...),
        contexto=(str, ...),
        assercao=(str, ...),
        justificativa_assercao=(str, ...),
        razao=(str, ...),
        justificativa_razao=(str, ...),
        nivel_bloom=(Literal[BLOOM_OBJETIVA], ...),
        tema=(str, ...),
        subtema=(str, ...),
        objetivo_cognitivo=(str, ...),
        fontes=(list[FonteGerada], Field(min_length=1)),
    )
    return _resultado("ResultadoAssercaoRazao", questao)


class AspectoGerado(BaseModel):
    """A fonte vive dentro do aspecto: pedir ao modelo um índice para
    outra lista é a referência cruzada que modelo pequeno erra, e assim
    aspecto sem fonte é irrepresentável."""

    texto: str
    fonte: FonteGerada


class QuestaoDiscursivaGerada(BaseModel):
    tipo: Literal["questao_discursiva"]
    contexto: str
    comando: str
    nivel_bloom: NivelBloom
    tema: str
    subtema: str
    objetivo_cognitivo: str
    aspectos_esperados: list[AspectoGerado] = Field(min_length=2, max_length=5)


class ResultadoGeracaoDiscursiva(BaseModel):
    resultado: QuestaoDiscursivaGerada | InsuficienciaFonte = Field(
        discriminator="tipo"
    )


class ItemDiscursivoGerado(BaseModel):
    comando: str
    aspectos_esperados: list[AspectoGerado] = Field(min_length=1, max_length=3)


def montar_schema_discursiva(n_itens: int | None = None) -> type[BaseModel]:
    if n_itens is None:
        return ResultadoGeracaoDiscursiva
    questao = create_model(
        f"QuestaoDiscursiva{n_itens}Itens",
        tipo=(Literal["questao_discursiva"], ...),
        contexto=(str, ...),
        itens=(
            list[ItemDiscursivoGerado],
            Field(min_length=n_itens, max_length=n_itens),
        ),
        nivel_bloom=(NivelBloom, ...),
        tema=(str, ...),
        subtema=(str, ...),
        objetivo_cognitivo=(str, ...),
    )
    return _resultado(f"ResultadoDiscursiva{n_itens}Itens", questao)


class DadoGerado(BaseModel):
    # Identificador Python ASCII: o avaliador o recusa se não for (SIMBOLO_VALIDO).
    simbolo: str
    valor: float
    # Sintaxe do pint ("m/s**2", "mol/L"); vazio para grandeza sem dimensão.
    unidade: str


class ErroTipicoGerado(BaseModel):
    descricao: str
    expressao: str


def montar_schema_calculo(k: int) -> type[BaseModel]:
    """Sem `alternativas`, `letra_correta` nem invalidações: o sistema
    calcula e escreve. `erros` tem K − 1 itens, um por distrator."""
    _validar_k(k)
    questao = create_model(
        f"QuestaoCalculo{k}",
        tipo=(Literal["questao"], ...),
        contexto=(str, ...),
        comando=(str, ...),
        dados=(list[DadoGerado], Field(min_length=1)),
        formula_citada=(str, ...),
        expressao=(str, ...),
        unidade_resultado=(str, ...),
        erros=(list[ErroTipicoGerado], Field(min_length=k - 1, max_length=k - 1)),
        objetivo_cognitivo=(str, ...),
        fontes=(list[FonteGerada], Field(min_length=1)),
        tema=(str, ...),
        subtema=(str, ...),
        nivel_bloom=(Literal[BLOOM_OBJETIVA], ...),
    )
    return _resultado(f"ResultadoCalculo{k}", questao)


def montar_schema(
    tipo: TipoQuestao,
    k: int,
    formato: FormatoItem = FormatoItem.PROPOSICAO,
    configuracao: tuple[bool, ...] | str | None = None,
    n_itens: int | None = None,
) -> type[BaseModel]:
    if tipo is TipoQuestao.DISCURSIVA:
        return montar_schema_discursiva(n_itens)
    if formato is FormatoItem.AFIRMATIVAS:
        return montar_schema_afirmativas(k, configuracao)
    if formato is FormatoItem.ASSERCAO_RAZAO:
        return montar_schema_assercao_razao()
    if formato is FormatoItem.CALCULO:
        return montar_schema_calculo(k)
    return montar_schema_objetiva(k)
