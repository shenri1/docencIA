from backend.app.core.config import settings
from backend.app.domain import TipoEventoAuditoria
from backend.app.models.auditoria import RegistroAuditoria
from backend.app.services.log_auditoria import (
    pseudonimo,
    pseudonimo_credencial,
    registrar_evento,
)
from backend.tests.services.critico.test_auditor_banco import auditar_um


def eventos(db, tipo: TipoEventoAuditoria) -> list[RegistroAuditoria]:
    return (
        db.query(RegistroAuditoria)
        .filter_by(tipo_evento=tipo.value)
        .order_by(RegistroAuditoria.id)
        .all()
    )


def test_pseudonimo_e_estavel_e_tem_64_hex():
    assert pseudonimo(17) == pseudonimo(17)
    assert len(pseudonimo(17)) == 64
    assert set(pseudonimo(17)) <= set("0123456789abcdef")
    assert pseudonimo(17) != pseudonimo(18)


def test_pseudonimo_muda_com_a_chave(monkeypatch):
    antes = pseudonimo(17)
    monkeypatch.setattr(settings, "pseudonimo_key", "outra-chave")
    assert pseudonimo(17) != antes


def test_dominios_de_docente_e_credencial_nao_colidem():
    assert pseudonimo(17) != pseudonimo_credencial("17")


def test_registrar_evento_nao_faz_commit(db_session, docente):
    registro = registrar_evento(
        db_session,
        TipoEventoAuditoria.EXCLUSAO,
        "bancos_questoes:1",
        docente.id,
        {"numeros": [1]},
    )
    assert registro.ator == pseudonimo(docente.id)
    assert registro.tipo_evento == "exclusao"
    db_session.rollback()
    assert eventos(db_session, TipoEventoAuditoria.EXCLUSAO) == []


def test_registrar_evento_sem_docente_tem_ator_nulo(db_session):
    registro = registrar_evento(
        db_session, TipoEventoAuditoria.LOGIN_FALHO, "docentes", None, {}
    )
    assert registro.ator is None


def test_auditoria_grava_o_pseudonimo_e_nao_a_credencial(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    auditar_um(
        db_session,
        docente,
        armazenamento,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
    )
    [registro] = eventos(db_session, TipoEventoAuditoria.AUDITORIA_QUESTAO)
    assert registro.ator == pseudonimo(docente.id)
    assert registro.ator != docente.credencial_institucional


import pytest

from backend.app.domain import EstadoQuestao
from backend.app.exceptions import NumerosInvalidosException
from backend.app.models.banco import BancoQuestoes
from backend.app.services.controle_banco.exclusao_service import (
    congelar_banco,
    excluir_questoes,
)
from backend.app.services.controle_banco.substituicao_service import (
    aceitar_substituicao,
    propor_substituicao,
    rejeitar_substituicao,
)
from backend.app.services.exportacao.exportacao_service import exportar
from backend.app.services.geracao.banco_service import gerar_banco
from backend.tests.fabrica_banco import criar_banco, criar_questao_objetiva
from backend.tests.services.geracao.duplos import ProvedorLLMFake
from backend.tests.services.geracao.test_banco_service import (
    preparar,
    roteiro,
    roteiro_variacao,
)
from backend.tests.services.provas.test_gabarito import provas_montadas

E = TipoEventoAuditoria


def banco_aberto(db, sessao, n=2):
    banco = criar_banco(db, sessao, n_objetivas=n)
    for numero in range(1, n + 1):
        criar_questao_objetiva(db, banco, numero=numero)
    db.commit()
    return banco


def test_questao_gerada(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake(roteiro(2)),
        sessao_rascunho,
        n_objetivas=2,
        n_discursivas=0,
        versao="v1",
    )
    registros = eventos(db_session, E.QUESTAO_GERADA)
    assert len(registros) == 2
    assert {r.ator for r in registros} == {pseudonimo(docente.id)}
    assert registros[0].entidade_afetada.startswith("questoes:")
    assert registros[0].payload["numero"] == 1
    assert registros[0].payload["estado"] == "ativa"
    assert registros[0].payload["tipo"] == "objetiva"
    assert registros[0].payload["modelo_geracao"] == "fake"


def test_exclusao(db_session, docente, sessao_rascunho):
    banco = banco_aberto(db_session, sessao_rascunho)
    excluir_questoes(db_session, docente, banco, [2], banco.revisao)
    [registro] = eventos(db_session, E.EXCLUSAO)
    assert registro.entidade_afetada == f"bancos_questoes:{banco.id}"
    assert registro.payload == {"numeros": [2], "revisao": banco.revisao}


def test_exclusao_recusada_nao_deixa_evento(db_session, docente, sessao_rascunho):
    banco = banco_aberto(db_session, sessao_rascunho)
    with pytest.raises(NumerosInvalidosException):
        excluir_questoes(db_session, docente, banco, [9], banco.revisao)
    db_session.rollback()
    assert eventos(db_session, E.EXCLUSAO) == []


def test_congelamento(db_session, docente, sessao_rascunho):
    banco = banco_aberto(db_session, sessao_rascunho)
    congelar_banco(db_session, docente, banco, banco.revisao)
    [registro] = eventos(db_session, E.CONGELAMENTO)
    assert registro.payload == {"revisao": banco.revisao, "n_atual": 2}


def test_substituicao_aceita_e_rejeitada(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake(roteiro(2)),
        sessao_rascunho,
        n_objetivas=2,
        n_discursivas=0,
        versao="v1",
    )
    banco = db_session.get(BancoQuestoes, resumo.banco_id)
    for numero in (1, 2):
        propor_substituicao(
            db_session,
            embeddings_fake,
            reranker_fake,
            ProvedorLLMFake(roteiro_variacao(1)),
            docente,
            banco,
            numero,
        )
    aceitar_substituicao(db_session, docente, banco, 1, banco.revisao)
    rejeitar_substituicao(db_session, docente, banco, 2)

    [aceita] = eventos(db_session, E.SUBSTITUICAO_ACEITA)
    assert aceita.payload["numero"] == 1
    assert set(aceita.payload) == {
        "numero",
        "questao_original_id",
        "candidata_id",
        "revisao",
    }
    [rejeitada] = eventos(db_session, E.SUBSTITUICAO_REJEITADA)
    assert set(rejeitada.payload) == {"numero", "questao_original_id", "candidata_id"}
    # As candidatas também passam por _persistir.
    candidatas = [
        r
        for r in eventos(db_session, E.QUESTAO_GERADA)
        if r.payload["estado"] == EstadoQuestao.CANDIDATA.value
    ]
    assert len(candidatas) == 2


def test_provas_montadas_e_exportacao(
    db_session, docente, sessao_rascunho, armazenamento
):
    banco, montadas = provas_montadas(db_session, docente, sessao_rascunho)
    [montagem] = eventos(db_session, E.PROVAS_MONTADAS)
    assert montagem.payload == {
        "prova_a_id": montadas.prova_a_id,
        "prova_b_id": montadas.prova_b_id,
        "revisao_banco": banco.revisao,
        "n_objetivas": 10,
        "n_discursivas": 0,
        "escolhida_pelo_docente": False,
    }

    registros = exportar(db_session, docente, armazenamento, banco)
    [exportacao] = eventos(db_session, E.EXPORTACAO_DOCX)
    assert exportacao.payload["revisao_banco"] == banco.revisao
    assert sorted(e["id"] for e in exportacao.payload["exportacoes"]) == sorted(
        r.id for r in registros
    )


def test_exportar_de_novo_nao_grava_evento(
    db_session, docente, sessao_rascunho, armazenamento
):
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    exportar(db_session, docente, armazenamento, banco)
    exportar(db_session, docente, armazenamento, banco)
    assert len(eventos(db_session, E.EXPORTACAO_DOCX)) == 1
