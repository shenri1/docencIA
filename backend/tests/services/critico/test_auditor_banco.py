from decimal import Decimal

import pytest

from backend.app.domain import EstadoQuestao
from backend.app.exceptions import (
    InconsistenciaDeEstadoException,
    PromptDivergenteException,
)
from backend.app.models.auditoria import RegistroAuditoria
from backend.app.models.banco import Alternativa, RelatorioImpacto
from backend.app.prompt.montagem import DIRETORIO_MODULOS
from backend.app.services.critico.auditor_service import (
    TIPO_EVENTO_AUDITORIA,
    auditar_banco,
    montar_resumo,
)
from backend.tests.fabrica_banco import (
    criar_banco,
    criar_questao_discursiva,
    criar_questao_objetiva,
)
from backend.tests.services.geracao.duplos import ProvedorLLMFake
from backend.tests.services.geracao.test_banco_service import preparar

FIX = "db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho"


def sem_achado() -> dict:
    return {"achados": []}


def banco_misto(db, armazenamento, sessao, objetivas=3, discursivas=1):
    preparar(db, armazenamento, sessao)
    banco = criar_banco(db, sessao, n_objetivas=objetivas, n_discursivas=discursivas)
    numero = 0
    for _ in range(objetivas):
        numero += 1
        criar_questao_objetiva(db, banco, numero=numero)
    for _ in range(discursivas):
        numero += 1
        criar_questao_discursiva(db, banco, numero=numero)
    db.commit()
    return banco


def _auditar(db, emb, rer, provedor, docente, banco):
    return auditar_banco(db, emb, rer, provedor, docente, banco)


def test_uma_chamada_por_objetiva_ativa_e_um_registro_cada(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_misto(db_session, armazenamento, sessao_rascunho)
    provedor = ProvedorLLMFake([sem_achado() for _ in range(3)])

    resumo = _auditar(db_session, embeddings_fake, reranker_fake, provedor, docente, banco)

    assert provedor.chamadas == 3
    assert resumo.auditadas == 3
    assert resumo.ja_auditadas == 0
    assert resumo.discursivas_ignoradas == 1
    assert resumo.revisao_auditada == banco.revisao
    registros = db_session.query(RegistroAuditoria).all()
    assert len(registros) == 3
    assert {r.tipo_evento for r in registros} == {TIPO_EVENTO_AUDITORIA}
    assert all(r.ator == docente.credencial_institucional for r in registros)


def test_payload_grava_revisao_modelo_e_versao_de_prompt(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_misto(
        db_session, armazenamento, sessao_rascunho, objetivas=1, discursivas=0
    )
    _auditar(
        db_session, embeddings_fake, reranker_fake,
        ProvedorLLMFake([sem_achado()]), docente, banco,
    )
    payload = db_session.query(RegistroAuditoria).one().payload
    assert payload["banco_id"] == banco.id
    assert payload["numero"] == 1
    assert payload["revisao_auditada"] == banco.revisao
    assert payload["modelo"] == "fake"
    assert payload["versao_prompt"] == "1.0.0"
    assert len(payload["hash_modulos"]) == 64
    assert payload["localizacoes_enviadas"]
    assert payload["achados"] == []


def test_auditar_nao_muda_nada_do_banco(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_misto(db_session, armazenamento, sessao_rascunho)
    antes = (banco.revisao, banco.n_atual, banco.estado)
    estados = {q.numero: q.estado for q in banco.questoes}

    _auditar(
        db_session, embeddings_fake, reranker_fake,
        ProvedorLLMFake([sem_achado() for _ in range(3)]), docente, banco,
    )

    assert (banco.revisao, banco.n_atual, banco.estado) == antes
    assert {q.numero: q.estado for q in banco.questoes} == estados
    assert db_session.query(RelatorioImpacto).count() == 0


def test_excluida_e_candidata_nao_geram_chamada(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_misto(
        db_session, armazenamento, sessao_rascunho, objetivas=3, discursivas=0
    )
    banco.questoes[0].estado = EstadoQuestao.EXCLUIDA
    banco.n_atual -= 1
    criar_questao_objetiva(db_session, banco, numero=2, estado=EstadoQuestao.CANDIDATA)
    db_session.commit()

    provedor = ProvedorLLMFake([sem_achado() for _ in range(2)])
    resumo = _auditar(db_session, embeddings_fake, reranker_fake, provedor, docente, banco)
    assert provedor.chamadas == 2
    assert resumo.auditadas == 2


def test_retomada_na_mesma_revisao_nao_audita_de_novo(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_misto(
        db_session, armazenamento, sessao_rascunho, objetivas=2, discursivas=0
    )
    _auditar(
        db_session, embeddings_fake, reranker_fake,
        ProvedorLLMFake([sem_achado(), sem_achado()]), docente, banco,
    )

    provedor = ProvedorLLMFake([])  # roteiro vazio: qualquer chamada estoura
    resumo = _auditar(db_session, embeddings_fake, reranker_fake, provedor, docente, banco)
    assert provedor.chamadas == 0
    assert resumo.auditadas == 2
    assert resumo.ja_auditadas == 2


def test_revisao_nova_reaudita_o_banco_inteiro(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """Substituição aceita incrementa banco.revisao: o banco mudou, e a
    auditoria anterior valia para outro estado."""
    banco = banco_misto(
        db_session, armazenamento, sessao_rascunho, objetivas=2, discursivas=0
    )
    _auditar(
        db_session, embeddings_fake, reranker_fake,
        ProvedorLLMFake([sem_achado(), sem_achado()]), docente, banco,
    )
    # Simula o efeito de uma substituição aceita. Como o banco não tem
    # RelatorioImpacto correspondente, a consistência (checagem 3) acusaria a
    # divergência: cria-se o relatório junto, como faria o service real.
    from backend.app.domain import EventoBanco
    from backend.app.services.controle_banco.estado import registrar_relatorio

    registrar_relatorio(db_session, banco, EventoBanco.SUBSTITUICAO)
    db_session.commit()

    provedor = ProvedorLLMFake([sem_achado(), sem_achado()])
    resumo = _auditar(db_session, embeddings_fake, reranker_fake, provedor, docente, banco)
    assert provedor.chamadas == 2
    assert resumo.ja_auditadas == 0
    assert db_session.query(RegistroAuditoria).count() == 4


def test_banco_sem_objetiva_ativa_nao_chama_o_provedor(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_misto(
        db_session, armazenamento, sessao_rascunho, objetivas=0, discursivas=2
    )
    provedor = ProvedorLLMFake([])
    resumo = _auditar(db_session, embeddings_fake, reranker_fake, provedor, docente, banco)
    assert provedor.chamadas == 0
    assert resumo.auditadas == 0
    assert resumo.discursivas_ignoradas == 2
    assert resumo.proporcao_com_achado == Decimal("0.00")


def test_proporcao_com_achado(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """Uma de quatro com achado = 25,00%. O achado vem da forma, sem depender do
    roteiro do duplo."""
    banco = banco_misto(
        db_session, armazenamento, sessao_rascunho, objetivas=4, discursivas=0
    )
    longa = (
        db_session.query(Alternativa)
        .filter(Alternativa.questao_id == banco.questoes[0].id, Alternativa.letra == "A")
        .one()
    )
    longa.texto = (
        "a fila preserva a ordem de descoberta dos vértices e garante visita por "
        "camadas de distância crescente a partir da origem escolhida"
    )
    db_session.commit()

    resumo = _auditar(
        db_session, embeddings_fake, reranker_fake,
        ProvedorLLMFake([sem_achado() for _ in range(4)]), docente, banco,
    )
    assert [q.numero for q in resumo.questoes] == [1]
    assert resumo.proporcao_com_achado == Decimal("25.00")


def test_divergencia_de_prompt_barra_antes_de_qualquer_chamada(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_misto(
        db_session, armazenamento, sessao_rascunho, objetivas=2, discursivas=0
    )
    caminho = DIRETORIO_MODULOS / "auditor" / "01_auditor.md"
    original = caminho.read_text(encoding="utf-8")
    caminho.write_text(original + "\n\nlinha extra\n", encoding="utf-8")
    provedor = ProvedorLLMFake([])
    try:
        with pytest.raises(PromptDivergenteException):
            _auditar(db_session, embeddings_fake, reranker_fake, provedor, docente, banco)
    finally:
        caminho.write_text(original, encoding="utf-8")
    assert provedor.chamadas == 0


def test_banco_incoerente_barra_a_auditoria(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_misto(
        db_session, armazenamento, sessao_rascunho, objetivas=2, discursivas=0
    )
    banco.n_atual = 99
    db_session.commit()
    provedor = ProvedorLLMFake([])
    with pytest.raises(InconsistenciaDeEstadoException):
        _auditar(db_session, embeddings_fake, reranker_fake, provedor, docente, banco)
    assert provedor.chamadas == 0


def test_montar_resumo_sem_nenhuma_auditoria(db_session, armazenamento, sessao_rascunho):
    banco = banco_misto(
        db_session, armazenamento, sessao_rascunho, objetivas=2, discursivas=1
    )
    resumo = montar_resumo(db_session, banco)
    assert (resumo.auditadas, resumo.ja_auditadas) == (0, 0)
    assert resumo.revisao_auditada == banco.revisao
    assert resumo.questoes == []


def test_montar_resumo_sem_ja_antes_iguala_os_contadores(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """No GET não houve chamada: `ja_auditadas` é igual a `auditadas`, e nenhum
    campo troca de significado entre os dois verbos."""
    banco = banco_misto(
        db_session, armazenamento, sessao_rascunho, objetivas=2, discursivas=0
    )
    _auditar(
        db_session, embeddings_fake, reranker_fake,
        ProvedorLLMFake([sem_achado(), sem_achado()]), docente, banco,
    )
    resumo = montar_resumo(db_session, banco)
    assert resumo.auditadas == resumo.ja_auditadas == 2
