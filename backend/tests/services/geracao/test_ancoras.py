import pytest

from backend.app.exceptions import MaterialInsuficienteParaBancoException
from backend.app.models.materiais import ChunkMaterial
from backend.app.services.geracao.ancoras import selecionar_ancoras
from backend.tests.services.rag.test_indexacao_service import criar_material


def semear_chunks(db, armazenamento, sessao, quantidade: int) -> None:
    material = criar_material(
        db, armazenamento, sessao, "P1", [("página 1", "conteúdo " * 40)]
    )
    db.query(ChunkMaterial).delete()
    for ordem in range(quantidade):
        db.add(
            ChunkMaterial(
                material_id=material.id,
                ordem=ordem,
                texto=f"trecho numero {ordem}",
                localizacao=f"página {ordem + 1}",
                vetor_embedding=[0.0] * 1023 + [1.0],
            )
        )
    db.commit()


def test_ancoras_sao_espacadas_e_nao_as_primeiras(
    db_session, armazenamento, sessao_rascunho
):
    """Percorrer sequencialmente geraria todas as questões a partir das
    primeiras páginas do primeiro arquivo."""
    semear_chunks(db_session, armazenamento, sessao_rascunho, 100)
    ancoras = selecionar_ancoras(db_session, sessao_rascunho, 10)
    assert [a.ordem for a in ancoras] == [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]


def test_ancoras_nunca_se_repetem(db_session, armazenamento, sessao_rascunho):
    semear_chunks(db_session, armazenamento, sessao_rascunho, 29)
    ancoras = selecionar_ancoras(db_session, sessao_rascunho, 29)
    assert len({a.id for a in ancoras}) == 29


def test_n_igual_ao_total_devolve_todos(db_session, armazenamento, sessao_rascunho):
    semear_chunks(db_session, armazenamento, sessao_rascunho, 7)
    assert [
        a.ordem for a in selecionar_ancoras(db_session, sessao_rascunho, 7)
    ] == list(range(7))


def test_selecao_e_deterministica(db_session, armazenamento, sessao_rascunho):
    """A retomada depende disto: recalcular a lista tem que dar a mesma."""
    semear_chunks(db_session, armazenamento, sessao_rascunho, 50)
    primeira = [a.id for a in selecionar_ancoras(db_session, sessao_rascunho, 13)]
    segunda = [a.id for a in selecionar_ancoras(db_session, sessao_rascunho, 13)]
    assert primeira == segunda


def test_chunks_insuficientes_falham_antes_de_qualquer_geracao(
    db_session, armazenamento, sessao_rascunho
):
    semear_chunks(db_session, armazenamento, sessao_rascunho, 12)
    with pytest.raises(MaterialInsuficienteParaBancoException) as capturado:
        selecionar_ancoras(db_session, sessao_rascunho, 29)
    assert capturado.value.corpo()["chunks_disponiveis"] == 12
    assert capturado.value.corpo()["questoes_pedidas"] == 29


def test_chunks_de_outra_sessao_nunca_viram_ancora(
    db_session, armazenamento, docente, sessao_rascunho
):
    """Teste da R2 no nível da ancoragem."""
    from backend.app.schemas.sessao import SessaoCriar
    from backend.app.services.sessao_service import criar_sessao

    semear_chunks(db_session, armazenamento, sessao_rascunho, 10)
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
    with pytest.raises(MaterialInsuficienteParaBancoException):
        selecionar_ancoras(db_session, outra, 1)
