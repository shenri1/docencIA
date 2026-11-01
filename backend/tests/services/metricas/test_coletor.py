import itertools
from types import SimpleNamespace

from backend.app.domain import FormatoItem
from backend.app.services.metricas.coletor import Coletor
from backend.app.services.provedor.tipos import UsoTokens


def _relogio():
    passos = itertools.count(0, 0.5)
    return lambda: next(passos)


def _candidato(chunk_id: int) -> dict:
    return {
        "chunk_id": chunk_id,
        "material": "P1",
        "localizacao": "p. 1",
        "score_vetorial": 0.5,
        "score_rerank": 0.5,
        "posicao_rerank": 0,
        "enviado": False,
    }


def test_medir_soma_etapas_sem_formato():
    coletor = Coletor(relogio=_relogio())
    with coletor.medir("rerank"):
        pass
    with coletor.medir("rerank"):
        pass
    assert coletor.tempos_ms["rerank"] == 1000


def test_medir_com_formato_lista_por_tentativa():
    coletor = Coletor(relogio=_relogio())
    with coletor.medir("gerador", FormatoItem.CALCULO):
        pass
    with coletor.medir("gerador", FormatoItem.PROPOSICAO):
        pass
    assert coletor.tempos_ms["gerador"] == [
        {"formato": "calculo", "ms": 500},
        {"formato": "proposicao", "ms": 500},
    ]


def test_medir_registra_mesmo_quando_o_bloco_levanta():
    coletor = Coletor(relogio=_relogio())
    try:
        with coletor.medir("juiz"):
            raise RuntimeError("x")
    except RuntimeError:
        pass
    assert coletor.tempos_ms["juiz"] == 500


def test_fechar_total_cobre_as_partes():
    coletor = Coletor(relogio=_relogio())
    with coletor.medir("busca_vetorial"):
        pass
    with coletor.medir("rerank"):
        pass
    coletor.fechar()
    assert coletor.tempos_ms["total"] >= (
        coletor.tempos_ms["busca_vetorial"] + coletor.tempos_ms["rerank"]
    )


def test_fechar_marca_enviados():
    coletor = Coletor()
    coletor.anotar_busca("ancora", "q", [_candidato(1), _candidato(2), _candidato(3)])
    coletor.anotar_busca("cruzamento:x", "q2", [_candidato(2)])
    coletor.trechos_enviados = [SimpleNamespace(chunk_id=2)]
    coletor.fechar()
    ancora, cruzamento = coletor.rag
    assert [c["enviado"] for c in ancora["candidatos"]] == [False, True, False]
    assert cruzamento["candidatos"][0]["enviado"] is True


def test_consulta_truncada_em_500():
    coletor = Coletor()
    coletor.anotar_busca("ancora", "a" * 900, [])
    assert len(coletor.rag[0]["consulta"]) == 500


def test_anotar_tokens_formato_opcional():
    coletor = Coletor()
    coletor.anotar_tokens("juiz", UsoTokens(10, 3), "qwen3:4b")
    coletor.anotar_tokens(
        "gerador", UsoTokens(100, 30), "qwen3.5:9b", FormatoItem.CALCULO
    )
    assert coletor.tokens == [
        {
            "papel": "juiz",
            "formato": None,
            "modelo": "qwen3:4b",
            "entrada": 10,
            "saida": 3,
        },
        {
            "papel": "gerador",
            "formato": "calculo",
            "modelo": "qwen3.5:9b",
            "entrada": 100,
            "saida": 30,
        },
    ]
