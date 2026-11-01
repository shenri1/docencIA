"""Duplos para a geração. Nenhum toca a rede."""

from pydantic import ValidationError

from backend.app.exceptions import RespostaLLMInvalidaException
from backend.app.services.provedor.tipos import RespostaLLM, UsoTokens


class ProvedorLLMFake:
    """Executa um roteiro: cada item é o dicionário que o modelo "devolveria".
    Exceções no roteiro são levantadas. Item fora do schema da requisição vira
    `RespostaLLMInvalidaException`, como nos clientes reais."""

    def __init__(self, roteiro: list) -> None:
        self.roteiro = list(roteiro)
        self.chamadas = 0
        self.requisicoes: list = []

    def gerar(self, sessao_id: int, requisicao) -> RespostaLLM:
        self.chamadas += 1
        self.requisicoes.append(requisicao)
        if not self.roteiro:
            raise AssertionError(
                f"ProvedorLLMFake ficou sem roteiro na chamada {self.chamadas}"
            )
        item = self.roteiro.pop(0)
        if isinstance(item, Exception):
            raise item
        try:
            conteudo = requisicao.formato.model_validate(item)
        except ValidationError as exc:
            raise RespostaLLMInvalidaException(str(exc)) from exc
        return RespostaLLM(
            conteudo=conteudo,
            uso=UsoTokens(entrada=1000, saida=500),
            provedor_id=1,
            modelo="fake",
        )


# 26 palavras: passa no mínimo da média (15) e é curto para a difícil (40).
CONTEXTO_MEDIA = (
    "Uma equipe de logística modela os bairros de uma cidade como vértices e as ruas "
    "como arestas de mesmo peso para planejar as entregas do dia."
)


def corpo_questao(
    k: int,
    identificador: str = "P1",
    contexto: str = "",
    enunciado: str = "Qual estrutura a busca em largura utiliza?",
    **sobrescritas,
) -> dict:
    """`enunciado` vira o `comando`. Com o contexto vazio, é também o enunciado
    montado, e os testes antigos leem o mesmo texto de antes."""
    questao = {
        "tipo": "questao",
        "contexto": contexto,
        "comando": enunciado,
        "nivel_bloom": "aplicar",
        "tema": "Grafos",
        "subtema": "Busca em largura",
        # 5 palavras e maiúscula: não dispara ALTERNATIVA_ROTULO nem
        # PONTUACAO_INCOERENTE contra o comando em pergunta.
        "alternativas": [
            {"texto": f"Alternativa número {i} do teste", "e_gemeo_malvado": i == 1}
            for i in range(k)
        ],
        "letra_correta": "A",
        "fontes": [
            {
                "identificador_material": identificador,
                "localizacao": "página 12",
                "trecho_base": "A busca em largura usa uma fila.",
            }
        ],
        "justificativa": {
            "objetivo_cognitivo": "identificar a estrutura",
            "justificativa_correta": "o trecho afirma o uso de fila",
            "invalidacao_distratores": [
                {"letra": "ABCDEFGHIJK"[i], "motivo": f"distrator {i}"}
                for i in range(1, k)
            ],
            "verificacao_unicidade": True,
            "texto_verificacao_unicidade": "nenhuma errada é defensável",
        },
    }
    questao.update(sobrescritas)
    return {"resultado": questao}


def corpo_discursiva(
    identificador: str = "P1",
    contexto: str = "",
    enunciado: str = "Explique por que a busca em largura usa uma fila.",
    **sobrescritas,
) -> dict:
    """Dois aspectos citando a MESMA fonte, de propósito: é o caso comum do
    modelo, e a persistência deve deduplicar."""
    fonte = {
        "identificador_material": identificador,
        "localizacao": "página 12",
        "trecho_base": "A busca em largura usa uma fila.",
    }
    questao = {
        "tipo": "questao_discursiva",
        "contexto": contexto,
        "comando": enunciado,
        "nivel_bloom": "entender",
        "tema": "Grafos",
        "subtema": "Busca em largura",
        "objetivo_cognitivo": "explicar a estrutura auxiliar da busca",
        "aspectos_esperados": [
            {"texto": "a fila preserva a ordem de descoberta", "fonte": fonte},
            {"texto": "a visita acontece por camadas de distância", "fonte": fonte},
        ],
    }
    questao.update(sobrescritas)
    return {"resultado": questao}


def corpo_insuficiencia(motivo: str = "não há trecho sobre o tema pedido") -> dict:
    return {
        "resultado": {
            "tipo": "insuficiencia_de_fonte",
            "informacao_faltante": motivo,
        }
    }


_FONTE = {
    "identificador_material": "P1",
    "localizacao": "página 12",
    "trecho_base": "A busca em largura usa uma fila.",
}
_NOMES = ("afirmativa_i", "afirmativa_ii", "afirmativa_iii", "afirmativa_iv")


def corpo_afirmativas(
    configuracao: tuple[bool, ...],
    textos: tuple[str, ...] | None = None,
    **sobrescritas,
) -> dict:
    textos = textos or tuple(
        f"Afirmação número {i + 1} sobre a busca em largura."
        for i in range(len(configuracao))
    )
    questao = {
        "tipo": "questao",
        "contexto": CONTEXTO_MEDIA,
        "comando": "A partir da situação descrita, avalie as afirmações a seguir.",
        **{
            nome: {
                "verdadeira": valor,
                "texto": textos[i],
                "justificativa": f"justificativa da afirmação {i + 1}",
            }
            for i, (nome, valor) in enumerate(zip(_NOMES, configuracao, strict=False))
        },
        "nivel_bloom": "analisar",
        "tema": "Grafos",
        "subtema": "Ordem de visita",
        "objetivo_cognitivo": "julgar afirmações sobre a ordem de visita",
        "fontes": [_FONTE],
    }
    questao.update(sobrescritas)
    return {"resultado": questao}


def corpo_assercao(**sobrescritas) -> dict:
    questao = {
        "tipo": "questao",
        "contexto": CONTEXTO_MEDIA,
        "assercao": "Os vértices descobertos esperam a vez numa estrutura própria.",
        "justificativa_assercao": "o trecho diz que a busca guarda os descobertos",
        "razao": "A ordem de saída dessa estrutura é a ordem de chegada.",
        "justificativa_razao": "fila devolve primeiro o mais antigo",
        "nivel_bloom": "avaliar",
        "tema": "Grafos",
        "subtema": "Fila na busca em largura",
        "objetivo_cognitivo": "avaliar a relação entre fila e ordem de visita",
        "fontes": [_FONTE],
    }
    questao.update(sobrescritas)
    return {"resultado": questao}


def corpo_discursiva_itens(n_itens: int, **sobrescritas) -> dict:
    comandos = (
        "Explique por que a busca em largura usa uma fila.",
        "Compare a busca em largura com a busca em profundidade.",
        "Avalie a busca em largura num grafo com pesos.",
    )
    questao = {
        "tipo": "questao_discursiva",
        "contexto": CONTEXTO_MEDIA,
        "itens": [
            {
                "comando": comandos[i],
                "aspectos_esperados": [
                    {"texto": f"aspecto do item {i + 1}", "fonte": _FONTE}
                ],
            }
            for i in range(n_itens)
        ],
        "nivel_bloom": "avaliar",
        "tema": "Grafos",
        "subtema": "Busca em largura",
        "objetivo_cognitivo": "analisar um caso de rotas",
    }
    questao.update(sobrescritas)
    return {"resultado": questao}


def corpo_calculo(k: int = 5, **sobrescritas) -> dict:
    """Saída do Gerador no formato CALCULO: g = 9,8 m/s², h = 5 m, correta
    9,90 m/s. Até K = 5 há erros típicos com valores distintos em m/s."""
    erros_possiveis = [
        ("esquece o fator 2 dentro da raiz", "sqrt(g * h)"),
        ("divide o resultado por 2", "sqrt(2 * g * h) / 2"),
        ("multiplica o resultado por 2", "sqrt(2 * g * h) * 2"),
        ("põe o fator 2 fora da raiz", "2 * sqrt(g * h)"),
    ]
    questao = {
        "tipo": "questao",
        "contexto": CONTEXTO_MEDIA,
        "comando": "Qual a velocidade ao chegar ao solo, dadas a altura h e a gravidade g?",
        "dados": [
            {"simbolo": "g", "valor": 9.8, "unidade": "m/s**2"},
            {"simbolo": "h", "valor": 5, "unidade": "m"},
        ],
        "formula_citada": "v = sqrt(2gh)",
        "expressao": "sqrt(2 * g * h)",
        "unidade_resultado": "m/s",
        "erros": [
            {"descricao": d, "expressao": e} for d, e in erros_possiveis[: k - 1]
        ],
        "nivel_bloom": "aplicar",
        "tema": "Queda livre",
        "subtema": "Velocidade final",
        "objetivo_cognitivo": "aplicar a fórmula da velocidade de queda",
        "fontes": [_FONTE],
    }
    questao.update(sobrescritas)
    return {"resultado": questao}
