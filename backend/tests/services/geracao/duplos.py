"""Duplos para a geração. Nenhum toca a rede."""

from backend.app.services.provedor.tipos import RespostaLLM, UsoTokens


class ProvedorLLMFake:
    """Executa um roteiro: cada item é o dicionário que o modelo "devolveria".
    Exceções no roteiro são levantadas."""

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
        return RespostaLLM(
            conteudo=requisicao.formato.model_validate(item),
            uso=UsoTokens(entrada=1000, saida=500),
            provedor_id=1,
            modelo="fake",
        )


def corpo_questao(k: int, identificador: str = "P1", **sobrescritas) -> dict:
    questao = {
        "tipo": "questao",
        "enunciado": "Qual estrutura a busca em largura utiliza?",
        "nivel_bloom": "aplicar",
        "tema": "Grafos",
        "subtema": "Busca em largura",
        "alternativas": [
            {"texto": f"opção {i}", "e_gemeo_malvado": i == 1} for i in range(k)
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


def corpo_discursiva(identificador: str = "P1", **sobrescritas) -> dict:
    """Dois aspectos citando a MESMA fonte, de propósito: é o caso comum do
    modelo, e a persistência deve deduplicar."""
    fonte = {
        "identificador_material": identificador,
        "localizacao": "página 12",
        "trecho_base": "A busca em largura usa uma fila.",
    }
    questao = {
        "tipo": "questao_discursiva",
        "enunciado": "Explique por que a busca em largura usa uma fila.",
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
