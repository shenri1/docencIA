import pytest

from backend.app.domain import EstadoSessao, FaixaDificuldade, NivelBloom
from backend.app.exceptions import FonteInvalidaException
from backend.app.services.calculo_distribuicao_service import calcular_distribuicao
from backend.app.services.geracao.agente_gerador_service import gerar_questao
from backend.app.services.rag.chunking import ConfigChunking
from backend.app.services.rag.indexacao_service import indexar_sessao
from backend.tests.services.geracao.duplos import (
    ProvedorLLMFake,
    corpo_insuficiencia,
    corpo_questao,
)
from backend.tests.services.rag.test_indexacao_service import criar_material

CFG_CHUNK = ConfigChunking(max_chars=1200, overlap_chars=200, min_chars=300)
DISTRIBUICAO = calcular_distribuicao(10, 30, 40, 30)


def preparar(db, armazenamento, embeddings, sessao):
    """Indexa um material real para que `buscar` tenha o que recuperar."""
    criar_material(
        db,
        armazenamento,
        sessao,
        "P1",
        [("página 12", "A busca em largura usa uma fila e visita por camadas. " * 12)],
    )
    indexar_sessao(db, armazenamento, embeddings, sessao, CFG_CHUNK)
    sessao.estado = EstadoSessao.MATERIAIS_CONFIRMADOS
    db.commit()
    from backend.app.services.geracao.ancoras import selecionar_ancoras

    return selecionar_ancoras(db, sessao, 1)[0]


def test_questao_valida_volta_preenchida(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    ancora = preparar(db_session, armazenamento, embeddings_fake, sessao_rascunho)
    provedor = ProvedorLLMFake([corpo_questao(sessao_rascunho.k_alternativas)])

    resultado = gerar_questao(
        db_session,
        embeddings_fake,
        reranker_fake,
        provedor,
        sessao_rascunho,
        ancora,
        FaixaDificuldade.MEDIA,
        numero=1,
        distribuicao=DISTRIBUICAO,
    )

    assert resultado.questao is not None
    assert resultado.motivo_insuficiencia is None
    assert resultado.numero == 1
    assert resultado.questao.nivel_bloom is NivelBloom.APLICAR
    assert len(resultado.questao.alternativas) == sessao_rascunho.k_alternativas
    # A fonte textual "P1" foi resolvida para o id real do material.
    assert resultado.fontes_resolvidas[0][0] > 0


def test_insuficiencia_volta_sem_questao_e_com_motivo(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    ancora = preparar(db_session, armazenamento, embeddings_fake, sessao_rascunho)
    provedor = ProvedorLLMFake([corpo_insuficiencia("faltou definir o critério")])

    resultado = gerar_questao(
        db_session,
        embeddings_fake,
        reranker_fake,
        provedor,
        sessao_rascunho,
        ancora,
        FaixaDificuldade.FACIL,
        numero=3,
        distribuicao=DISTRIBUICAO,
    )

    assert resultado.questao is None
    assert "critério" in resultado.motivo_insuficiencia
    assert resultado.numero == 3
    assert resultado.localizacao_ancora == ancora.localizacao


def test_fonte_inventada_e_rejeitada(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """Sem esta checagem a rastreabilidade seria ficção: o modelo
    pode citar material que nunca lhe foi mostrado."""
    ancora = preparar(db_session, armazenamento, embeddings_fake, sessao_rascunho)
    provedor = ProvedorLLMFake(
        [corpo_questao(sessao_rascunho.k_alternativas, identificador="P9")]
    )

    with pytest.raises(FonteInvalidaException) as capturado:
        gerar_questao(
            db_session,
            embeddings_fake,
            reranker_fake,
            provedor,
            sessao_rascunho,
            ancora,
            FaixaDificuldade.MEDIA,
            numero=1,
            distribuicao=DISTRIBUICAO,
        )
    assert capturado.value.corpo()["identificador"] == "P9"


def test_o_texto_da_ancora_vira_a_consulta_do_rag(
    db_session,
    armazenamento,
    embeddings_fake,
    reranker_fake,
    sessao_rascunho,
    monkeypatch,
):
    """A âncora decide sobre o que perguntar; o RAG só traz o contexto vizinho."""
    from backend.app.services.geracao import agente_gerador_service as mod

    ancora = preparar(db_session, armazenamento, embeddings_fake, sessao_rascunho)
    consultas: list[str] = []
    original = mod.buscar

    def espiao(db, emb, rer, sessao, consulta, k, candidatos):
        consultas.append(consulta)
        return original(db, emb, rer, sessao, consulta, k, candidatos)

    monkeypatch.setattr(mod, "buscar", espiao)
    gerar_questao(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake([corpo_questao(sessao_rascunho.k_alternativas)]),
        sessao_rascunho,
        ancora,
        FaixaDificuldade.MEDIA,
        numero=1,
        distribuicao=DISTRIBUICAO,
    )
    assert consultas == [ancora.texto]


def test_a_faixa_pedida_aparece_na_mensagem_de_usuario(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """faixa_dificuldade não está no schema de saída, então a única forma de o
    modelo saber qual faixa gerar é o texto do pedido."""
    ancora = preparar(db_session, armazenamento, embeddings_fake, sessao_rascunho)

    class ProvedorEspiao(ProvedorLLMFake):
        def gerar(self, sessao_id, requisicao):
            self.ultima = requisicao
            return super().gerar(sessao_id, requisicao)

    provedor = ProvedorEspiao([corpo_questao(sessao_rascunho.k_alternativas)])
    gerar_questao(
        db_session,
        embeddings_fake,
        reranker_fake,
        provedor,
        sessao_rascunho,
        ancora,
        FaixaDificuldade.DIFICIL,
        numero=1,
        distribuicao=DISTRIBUICAO,
    )
    assert "dificil" in provedor.ultima.usuario.lower()
    assert "P1" in provedor.ultima.usuario
