from types import SimpleNamespace

from backend.app.domain import TipoQuestao
from backend.app.services.metricas.aderencia import (
    medir_aderencia,
    tema_da_sessao,
    texto_da_questao,
)
from backend.app.services.metricas.coletor import Coletor
from backend.app.services.metricas.juiz import (
    AvaliacaoAderencia,
    FalhaJuizException,
    JuizFake,
)
from backend.app.services.rag.embeddings import EmbeddingsFake

SESSAO = SimpleNamespace(tema_escopo="Grafos", disciplina="Algoritmos")


def _objetiva():
    return SimpleNamespace(
        tipo=TipoQuestao.OBJETIVA,
        enunciado="Qual estrutura a BFS usa?",
        alternativas=[
            SimpleNamespace(letra="B", texto="Pilha", correta=False),
            SimpleNamespace(letra="A", texto="Fila", correta=True),
        ],
        aspectos=[],
        justificativa=SimpleNamespace(objetivo_cognitivo="SEGREDO"),
    )


def _discursiva():
    return SimpleNamespace(
        tipo=TipoQuestao.DISCURSIVA,
        enunciado="Explique a BFS.",
        alternativas=[],
        aspectos=[
            SimpleNamespace(texto="usa fila"),
            SimpleNamespace(texto="por níveis"),
        ],
        justificativa=SimpleNamespace(objetivo_cognitivo="SEGREDO"),
    )


def test_tema_usa_tema_escopo():
    assert tema_da_sessao(SESSAO) == ("Grafos", "tema_escopo")


def test_tema_cai_para_disciplina():
    sessao = SimpleNamespace(tema_escopo=None, disciplina="Algoritmos")
    assert tema_da_sessao(sessao) == ("Algoritmos", "disciplina")


def test_texto_da_questao_objetiva_sem_justificativa():
    texto = texto_da_questao(_objetiva())
    assert texto == "Qual estrutura a BFS usa?\nA) Fila\nB) Pilha"
    assert "SEGREDO" not in texto


def test_texto_da_questao_discursiva_usa_aspectos():
    assert texto_da_questao(_discursiva()) == (
        "Explique a BFS.\n- usa fila\n- por níveis"
    )


def test_juiz_ok_grava_notas_e_tokens():
    coletor = Coletor()
    resultado = medir_aderencia(
        _objetiva(), SESSAO, ["BFS usa fila."], EmbeddingsFake(), JuizFake(), coletor
    )
    assert resultado["tema"] == {"origem": "tema_escopo", "texto": "Grafos"}
    assert resultado["juiz"]["nota_tema"] == 5
    assert resultado["juiz"]["modelo"] == "juiz-fake"
    assert resultado["juiz"]["versao_prompt"].startswith("aderencia@")
    assert -1.0 <= resultado["embedding"]["cos_tema"] <= 1.0
    assert resultado["embedding"]["cos_trecho_max"] is not None
    assert [t["papel"] for t in coletor.tokens] == ["juiz"]
    assert {"juiz", "embedding_aderencia"} <= set(coletor.tempos_ms)


def test_juiz_falha_vira_erro_e_nao_levanta():
    resultado = medir_aderencia(
        _objetiva(),
        SESSAO,
        ["t"],
        EmbeddingsFake(),
        JuizFake(FalhaJuizException("timeout")),
        Coletor(),
    )
    assert resultado["juiz"] == {"erro": "timeout"}
    assert "cos_tema" in resultado["embedding"]


def test_juiz_ausente_vira_erro():
    resultado = medir_aderencia(
        _objetiva(), SESSAO, ["t"], EmbeddingsFake(), None, Coletor()
    )
    assert resultado["juiz"] == {"erro": "juiz não configurado"}


class EmbeddingsQuebrado:
    dimensao = 4

    def embutir_documentos(self, textos):
        raise RuntimeError("ollama fora")


def test_embedding_falha_vira_erro_e_juiz_ainda_roda():
    resultado = medir_aderencia(
        _objetiva(), SESSAO, ["t"], EmbeddingsQuebrado(), JuizFake(), Coletor()
    )
    assert resultado["embedding"] == {"erro": "ollama fora"}
    assert resultado["juiz"]["nota_trecho"] == 5


def test_sem_trechos_citados_cos_trecho_e_none():
    resultado = medir_aderencia(
        _objetiva(), SESSAO, [], EmbeddingsFake(), JuizFake(), Coletor()
    )
    assert resultado["embedding"]["cos_trecho_max"] is None


def test_juiz_recebe_so_tema_questao_e_trechos():
    juiz = JuizFake(AvaliacaoAderencia(nota_tema=3, nota_trecho=2, justificativa="x"))
    medir_aderencia(
        _objetiva(), SESSAO, ["BFS usa fila."], EmbeddingsFake(), juiz, Coletor()
    )
    tema, questao, trechos = juiz.chamadas[0]
    assert tema == "Grafos"
    assert questao.startswith("Qual estrutura a BFS usa?\nA) Fila\nB) Pilha")
    assert "Resposta correta: A" in questao
    assert "SEGREDO" not in questao
    assert trechos == ["BFS usa fila."]
