import pytest

from backend.app.domain import EstadoSessao
from backend.app.exceptions import (
    IndiceNaoConfirmadoException,
    SessaoNaoIndexadaException,
)
from backend.app.services.rag.chunking import ConfigChunking
from backend.app.services.rag.indexacao_service import indexar_sessao
from backend.app.services.rag.rerank import RerankerFake
from backend.app.services.rag.retrieval_service import buscar
from backend.tests.services.rag.test_indexacao_service import criar_material

CFG = ConfigChunking(max_chars=1200, overlap_chars=200, min_chars=300)


class RerankerInvertido:
    """Inverte a ordem recebida: é o duplo que prova que a ordem final vem do
    reranker, e não da distância de cosseno."""

    def reordenar(self, consulta, documentos, top_n):
        return [(i, float(i)) for i in reversed(range(len(documentos)))][:top_n]


def indexar(db, armazenamento, embeddings, sessao, identificador, blocos):
    criar_material(db, armazenamento, sessao, identificador, blocos)
    indexar_sessao(db, armazenamento, embeddings, sessao, CFG)
    sessao.estado = EstadoSessao.MATERIAIS_CONFIRMADOS
    db.commit()


def test_busca_em_sessao_nao_confirmada_e_409(
    db_session, embeddings_fake, reranker_fake, sessao_rascunho
):
    with pytest.raises(IndiceNaoConfirmadoException):
        buscar(
            db_session,
            embeddings_fake,
            reranker_fake,
            sessao_rascunho,
            "grafos",
            k=5,
            candidatos=20,
        )


def test_sessao_confirmada_sem_chunk_e_409_proprio(
    db_session, embeddings_fake, reranker_fake, sessao_rascunho
):
    sessao_rascunho.estado = EstadoSessao.MATERIAIS_CONFIRMADOS
    db_session.commit()
    with pytest.raises(SessaoNaoIndexadaException):
        buscar(
            db_session,
            embeddings_fake,
            reranker_fake,
            sessao_rascunho,
            "grafos",
            k=5,
            candidatos=20,
        )


def test_trechos_carregam_fonte_rastreavel(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    indexar(
        db_session,
        armazenamento,
        embeddings_fake,
        sessao_rascunho,
        "P1",
        [("página 1", "busca em largura percorre o grafo por níveis " * 12)],
    )
    trechos = buscar(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        "busca em largura",
        k=5,
        candidatos=20,
    )
    assert trechos
    assert trechos[0].identificador_curto == "P1"
    assert trechos[0].localizacao
    assert 0.0 <= trechos[0].score <= 1.0


def test_ordem_final_vem_do_reranker(
    db_session, armazenamento, embeddings_fake, sessao_rascunho
):
    indexar(
        db_session,
        armazenamento,
        embeddings_fake,
        sessao_rascunho,
        "P1",
        [("página 1", f"tema {n} " * 60) for n in range(1, 5)],
    )
    com_fake = buscar(
        db_session,
        embeddings_fake,
        RerankerFake(),
        sessao_rascunho,
        "tema",
        k=4,
        candidatos=20,
    )
    invertido = buscar(
        db_session,
        embeddings_fake,
        RerankerInvertido(),
        sessao_rascunho,
        "tema",
        k=4,
        candidatos=20,
    )
    assert [t.texto for t in invertido] == [t.texto for t in com_fake][::-1]


def test_k_limita_a_saida(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    indexar(
        db_session,
        armazenamento,
        embeddings_fake,
        sessao_rascunho,
        "P1",
        [("página 1", f"assunto {n} " * 60) for n in range(1, 6)],
    )
    assert (
        len(
            buscar(
                db_session,
                embeddings_fake,
                reranker_fake,
                sessao_rascunho,
                "assunto",
                k=2,
                candidatos=20,
            )
        )
        == 2
    )


def test_busca_nunca_alcanca_chunk_de_outra_sessao(
    db_session,
    armazenamento,
    embeddings_fake,
    reranker_fake,
    docente,
    sessao_rascunho,
):
    """Este é o teste da R2: a restrição está no SQL, não no prompt."""
    from backend.app.schemas.sessao import SessaoCriar
    from backend.app.services.sessao_service import criar_sessao

    texto = "conteúdo idêntico nas duas sessões " * 12
    indexar(
        db_session,
        armazenamento,
        embeddings_fake,
        sessao_rascunho,
        "P1",
        [("página 1", texto)],
    )

    outra = criar_sessao(
        db_session,
        docente,
        SessaoCriar(
            disciplina="Outra",
            periodo="2026.2",
            tema_escopo=None,
            area_do_conhecimento=None,
            k_alternativas=4,
            p_f=30,
            p_m=40,
            p_d=30,
        ),
    )
    indexar(
        db_session, armazenamento, embeddings_fake, outra, "P9", [("página 1", texto)]
    )

    trechos = buscar(
        db_session,
        embeddings_fake,
        reranker_fake,
        outra,
        "conteúdo idêntico",
        k=10,
        candidatos=20,
    )
    assert trechos
    assert {t.identificador_curto for t in trechos} == {"P9"}


def test_sessao_sem_chunk_nao_chama_embeddings(
    db_session, reranker_fake, sessao_rascunho
):
    """Busca em sessão confirmada sem chunk levanta 409 sem pagar embedding."""
    sessao_rascunho.estado = EstadoSessao.MATERIAIS_CONFIRMADOS
    db_session.commit()

    class Spy:
        dimensao = 1024

        def __init__(self):
            self.chamadas = 0

        def embutir_documentos(self, textos):
            raise AssertionError("não deveria embutir documentos")

        def embutir_consulta(self, texto):
            self.chamadas += 1
            return [0.0] * self.dimensao

    spy = Spy()
    with pytest.raises(SessaoNaoIndexadaException):
        buscar(
            db_session,
            spy,
            reranker_fake,
            sessao_rascunho,
            "grafos",
            k=5,
            candidatos=20,
        )
    assert spy.chamadas == 0
