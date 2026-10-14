from datetime import UTC, datetime

import pytest

from backend.app.domain import (
    ComandoOrquestrador,
    EstadoBanco,
    EstadoSessao,
    EventoBanco,
    Marco,
    TipoGabarito,
)
from backend.app.exceptions import (
    CamposDoMarcoException,
    ComandoForaDoMarcoException,
    NumerosInvalidosException,
    RevisaoDesatualizadaException,
)
from backend.app.models.materiais import ChunkMaterial
from backend.app.models.provas import ExportacaoDocx
from backend.app.schemas.orquestrador import (
    ComandoAuditar,
    ComandoExcluir,
    ComandoProsseguir,
)
from backend.app.services.orquestrador.orquestrador_service import executar_comando
from backend.app.services.prompt_mestre_service import ativar, registrar_versao
from backend.tests.fabrica_banco import criar_banco, criar_questao_objetiva
from backend.tests.services.geracao.duplos import ProvedorLLMFake
from backend.tests.services.geracao.test_banco_service import (
    PARAMS_PROMPT,
    preparar,
    roteiro,
)
from backend.tests.services.orquestrador.test_marco import banco_congelado
from backend.tests.services.provas.test_gabarito import provas_montadas
from backend.tests.services.rag.test_indexacao_service import criar_material


@pytest.fixture()
def executar(db_session, docente, armazenamento, embeddings_fake, reranker_fake):
    def _executar(sessao, comando, provedor=None):
        return executar_comando(
            db_session,
            docente,
            sessao,
            comando,
            armazenamento=armazenamento,
            embeddings=embeddings_fake,
            reranker=reranker_fake,
            obter_provedor=lambda: provedor,
        )

    return _executar


def sessao_com_banco(sessao):
    """Banco montado pela fábrica não passa pela geração: sem isto a sessão
    fica em RASCUNHO, estado que não coexiste com banco, e o alvo é o M1."""
    sessao.estado = EstadoSessao.BANCO_GERADO


def prosseguir(**campos) -> ComandoProsseguir:
    return ComandoProsseguir(comando="prosseguir", **campos)


def material_indexado(db, armazenamento, sessao, chunks=30):
    """Prompt ativo e material já indexado, com a sessão AINDA em rascunho: o
    prosseguir do M1 só confirma, sem depender do chunking."""
    registrar_versao(db, "1.0.0", "docente", PARAMS_PROMPT)
    ativar(db, "1.0.0")
    material = criar_material(
        db, armazenamento, sessao, "P1", [("página 1", "conteúdo " * 40)]
    )
    for ordem in range(chunks):
        db.add(
            ChunkMaterial(
                material_id=material.id,
                ordem=ordem,
                texto=f"trecho numero {ordem} sobre busca em largura",
                localizacao=f"página {ordem + 1}",
                vetor_embedding=[0.0] * 1023 + [1.0],
            )
        )
    material.indexado_em = datetime.now(UTC)
    db.commit()


def test_prosseguir_no_m1_confirma_o_indice(
    executar, db_session, armazenamento, sessao_rascunho
):
    material_indexado(db_session, armazenamento, sessao_rascunho)
    resultado = executar(sessao_rascunho, prosseguir())

    assert resultado.comando is ComandoOrquestrador.PROSSEGUIR
    assert resultado.marco_executado is Marco.M1_MATERIAIS
    assert resultado.indice.confirmado is True
    assert [m.identificador_curto for m in resultado.indice.materiais] == ["P1"]
    assert resultado.marco.marco is Marco.M2_BANCO


def test_prosseguir_no_m1_com_versao_e_campo_que_sobra(executar, sessao_rascunho):
    with pytest.raises(CamposDoMarcoException) as erro:
        executar(sessao_rascunho, prosseguir(versao="v1"))
    assert erro.value.extras["sobrando"] == ["versao"]
    assert erro.value.extras["marco"] == "m1_materiais"


def test_prosseguir_no_m2_gera_o_banco(
    executar, db_session, armazenamento, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    resultado = executar(
        sessao_rascunho,
        prosseguir(versao="v1", n_objetivas=2, n_discursivas=0),
        ProvedorLLMFake(roteiro(2)),
    )

    assert resultado.marco_executado is Marco.M2_BANCO
    assert resultado.banco.geradas == 2
    [banco] = resultado.marco.bancos
    assert (banco.versao, banco.marco) == ("v1", Marco.M3_EXCLUSOES)


def test_prosseguir_sem_versao_depois_do_m1_falta_versao(
    executar, db_session, armazenamento, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    with pytest.raises(CamposDoMarcoException) as erro:
        executar(sessao_rascunho, prosseguir(n_objetivas=2, n_discursivas=0))
    assert erro.value.extras["faltando"] == ["versao"]


def test_prosseguir_no_m3_congela_e_cataloga(executar, db_session, sessao_rascunho):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=2)
    criar_questao_objetiva(db_session, banco, numero=1)
    criar_questao_objetiva(db_session, banco, numero=2)
    sessao_com_banco(sessao_rascunho)
    db_session.commit()

    resultado = executar(
        sessao_rascunho, prosseguir(versao="v1", revisao_esperada=banco.revisao)
    )
    assert resultado.marco_executado is Marco.M3_EXCLUSOES
    assert resultado.relatorio.evento is EventoBanco.CONGELAMENTO
    assert [i.numero for i in resultado.catalogo] == [1, 2]
    assert banco.estado is EstadoBanco.CONGELADO
    assert resultado.marco.bancos[0].marco is Marco.M6_PROVAS


def test_prosseguir_com_campos_do_m6_no_m3_nao_congela(
    executar, db_session, sessao_rascunho
):
    """Um pedido de montagem reenviado com o banco aberto congelaria o banco,
    e congelar é irreversível."""
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=1)
    criar_questao_objetiva(db_session, banco, numero=1)
    sessao_com_banco(sessao_rascunho)
    db_session.commit()

    with pytest.raises(CamposDoMarcoException) as erro:
        executar(
            sessao_rascunho,
            prosseguir(
                versao="v1",
                revisao_esperada=banco.revisao,
                n_objetivas=1,
                n_discursivas=0,
            ),
        )
    assert erro.value.extras["sobrando"] == ["n_objetivas", "n_discursivas"]
    assert banco.estado is EstadoBanco.ABERTO


def test_prosseguir_no_m6_monta_e_da_os_gabaritos_simples(
    executar, db_session, docente, sessao_rascunho
):
    banco = banco_congelado(db_session, docente, sessao_rascunho)
    resultado = executar(
        sessao_rascunho,
        prosseguir(
            versao="v1",
            revisao_esperada=banco.revisao,
            n_objetivas=10,
            n_discursivas=0,
        ),
    )
    assert resultado.marco_executado is Marco.M6_PROVAS
    assert resultado.provas.verificacao.violacoes == []
    assert [g.modalidade for g in resultado.gabaritos] == [
        TipoGabarito.SIMPLES,
        TipoGabarito.SIMPLES,
    ]
    assert [g.prova_id for g in resultado.gabaritos] == [
        resultado.provas.prova_a_id,
        resultado.provas.prova_b_id,
    ]
    assert resultado.marco.bancos[0].marco is Marco.M10_DOCX


def test_prosseguir_no_m10_exporta(executar, db_session, docente, sessao_rascunho):
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    resultado = executar(
        sessao_rascunho, prosseguir(versao="v1", revisao_esperada=banco.revisao)
    )
    assert resultado.marco_executado is Marco.M10_DOCX
    assert len(resultado.exportacoes) == 2
    assert resultado.marco.bancos[0].marco is Marco.CONCLUIDO


def test_revisao_velha_no_m10_e_409_e_nao_exporta(
    executar, db_session, docente, sessao_rascunho
):
    """A rota de exportação não pede revisao_esperada; o orquestrador pede."""
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    with pytest.raises(RevisaoDesatualizadaException):
        executar(
            sessao_rascunho,
            prosseguir(versao="v1", revisao_esperada=banco.revisao + 7),
        )
    assert db_session.query(ExportacaoDocx).count() == 0


def test_excluir_no_m3(executar, db_session, sessao_rascunho):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=2)
    criar_questao_objetiva(db_session, banco, numero=1)
    criar_questao_objetiva(db_session, banco, numero=2)
    sessao_com_banco(sessao_rascunho)
    db_session.commit()
    revisao = banco.revisao

    resultado = executar(
        sessao_rascunho,
        ComandoExcluir(
            comando="excluir", versao="v1", revisao_esperada=revisao, numeros=[2]
        ),
    )
    assert resultado.comando is ComandoOrquestrador.EXCLUIR
    assert resultado.relatorio.evento is EventoBanco.EXCLUSAO
    assert resultado.marco.bancos[0].revisao == revisao + 1


def test_excluir_numero_inexistente_passa_a_excecao_da_etapa_11(
    executar, db_session, sessao_rascunho
):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=1)
    criar_questao_objetiva(db_session, banco, numero=1)
    sessao_com_banco(sessao_rascunho)
    db_session.commit()
    with pytest.raises(NumerosInvalidosException):
        executar(
            sessao_rascunho,
            ComandoExcluir(
                comando="excluir",
                versao="v1",
                revisao_esperada=banco.revisao,
                numeros=[9],
            ),
        )


def test_excluir_no_m6_e_fora_do_marco(executar, db_session, docente, sessao_rascunho):
    banco = banco_congelado(db_session, docente, sessao_rascunho)
    with pytest.raises(ComandoForaDoMarcoException) as erro:
        executar(
            sessao_rascunho,
            ComandoExcluir(
                comando="excluir",
                versao="v1",
                revisao_esperada=banco.revisao,
                numeros=[1],
            ),
        )
    assert erro.value.extras["marco"] == "m6_provas"
    assert erro.value.extras["comandos_aceitos"] == ["prosseguir", "auditar"]


def test_auditar_versao_inexistente_e_fora_do_marco(
    executar, db_session, armazenamento, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    with pytest.raises(ComandoForaDoMarcoException) as erro:
        executar(sessao_rascunho, ComandoAuditar(comando="auditar", versao="v9"))
    assert erro.value.extras["marco"] == "m2_banco"


def test_excluir_com_sessao_em_m1_e_fora_do_marco(executar, sessao_rascunho):
    with pytest.raises(ComandoForaDoMarcoException) as erro:
        executar(
            sessao_rascunho,
            ComandoExcluir(
                comando="excluir", versao="v1", revisao_esperada=0, numeros=[1]
            ),
        )
    assert erro.value.extras["marco"] == "m1_materiais"


def test_auditar_no_m3(executar, db_session, armazenamento, sessao_rascunho):
    preparar(db_session, armazenamento, sessao_rascunho)
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=2)
    criar_questao_objetiva(db_session, banco, numero=1)
    criar_questao_objetiva(db_session, banco, numero=2)
    db_session.commit()

    resultado = executar(
        sessao_rascunho,
        ComandoAuditar(comando="auditar", versao="v1"),
        ProvedorLLMFake([{"achados": []}, {"achados": []}]),
    )
    assert resultado.auditoria.auditadas == 2
    assert resultado.marco.bancos[0].objetivas_auditadas == 2


def test_bloqueado_recusa_prosseguir_com_o_motivo(
    executar, db_session, docente, sessao_rascunho
):
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    banco.revisao += 1
    db_session.commit()
    with pytest.raises(ComandoForaDoMarcoException) as erro:
        executar(
            sessao_rascunho, prosseguir(versao="v1", revisao_esperada=banco.revisao)
        )
    assert erro.value.extras["marco"] == "bloqueado"
    assert "revisão" in erro.value.extras["motivo"]
