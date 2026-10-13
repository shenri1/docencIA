from sqlalchemy import func, select

from backend.app.domain import FormatoItem, TipoEventoAuditoria, TipoQuestao
from backend.app.models.auditoria import RegistroAuditoria
from backend.app.models.banco import Questao
from backend.app.models.orientacoes import questoes_orientacoes
from backend.app.services.geracao import busca_orientada
from backend.app.services.geracao.ancoras import selecionar_ancoras
from backend.app.services.geracao.banco_service import (
    _montar_plano,
    _obter_ou_criar_banco,
    gerar_banco,
    produzir_questao,
)
from backend.app.services.orientacoes.orientacao_service import (
    criar_orientacao_questao,
    criar_orientacao_sessao,
    desativar,
)
from backend.tests.services.geracao.duplos import (
    CONTEXTO_MEDIA,
    ProvedorLLMFake,
    corpo_insuficiencia,
    corpo_questao,
)
from backend.tests.services.geracao.test_banco_service import preparar, roteiro


def _payload_da_geracao(db):
    return db.scalars(
        select(RegistroAuditoria.payload).where(
            RegistroAuditoria.tipo_evento == TipoEventoAuditoria.QUESTAO_GERADA.value
        )
    ).one()


def test_gerar_banco_manda_as_vigentes_ao_gerador_e_ao_critico(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    ativa = criar_orientacao_sessao(db_session, docente, sessao_rascunho, "exemplos práticos")
    inativa = criar_orientacao_sessao(db_session, docente, sessao_rascunho, "texto desativado")
    desativar(db_session, docente, sessao_rascunho, inativa.id)
    provedor = ProvedorLLMFake(roteiro(1))

    gerar_banco(
        db_session, embeddings_fake, reranker_fake, provedor, sessao_rascunho,
        n_objetivas=1, n_discursivas=0, versao="v1",
    )

    gerador, critico = (r.usuario for r in provedor.requisicoes)
    for usuario in (gerador, critico):
        assert "Orientações do docente:\n1. Mudar: exemplos práticos" in usuario
        assert "texto desativado" not in usuario
    questao = db_session.scalars(select(Questao)).one()
    assert [o.id for o in questao.orientacoes] == [ativa.id]
    payload = _payload_da_geracao(db_session)
    assert payload["n_orientacoes"] == 1
    assert payload["com_cruzamento"] is False
    assert payload["orientacoes_ids"] == [ativa.id]
    assert "exemplos práticos" not in str(payload)


def test_geracao_sem_orientacoes_nao_grava_ligacao(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    gerar_banco(
        db_session, embeddings_fake, reranker_fake, ProvedorLLMFake(roteiro(1)),
        sessao_rascunho, n_objetivas=1, n_discursivas=0, versao="v1",
    )
    assert db_session.scalar(select(func.count()).select_from(questoes_orientacoes)) == 0
    payload = _payload_da_geracao(db_session)
    assert (payload["n_orientacoes"], payload["orientacoes_ids"]) == (0, [])


def test_recuo_com_cruzamento_nao_busca_de_novo(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho,
    monkeypatch,
):
    buscar = busca_orientada.buscar
    consultas: list[str] = []

    def contar(db, emb, rer, sessao, consulta, k, candidatos):
        consultas.append(consulta)
        return buscar(db, emb, rer, sessao, consulta, k, candidatos)

    monkeypatch.setattr(busca_orientada, "buscar", contar)
    preparar(db_session, armazenamento, sessao_rascunho)
    banco = _obter_ou_criar_banco(db_session, sessao_rascunho, "v1", 10, 0)
    cruzada = criar_orientacao_questao(
        db_session, docente, banco, 1, "busca em profundidade", None, True
    )
    ancora = selecionar_ancoras(db_session, sessao_rascunho, 10)[0]
    plano = _montar_plano(sessao_rascunho, 10, 0)
    provedor = ProvedorLLMFake(
        [corpo_insuficiencia(), corpo_questao(5, contexto=CONTEXTO_MEDIA),
         corpo_questao(5, contexto=CONTEXTO_MEDIA)]
    )

    produzida = produzir_questao(
        db_session, embeddings_fake, reranker_fake, provedor, sessao_rascunho, banco, 1,
        TipoQuestao.OBJETIVA, plano[4].faixa, ancora, plano[4].distribuicao,
        formato=FormatoItem.AFIRMATIVAS, configuracao=(True, False, True),
        orientacoes=[cruzada],
    )

    assert produzida.questao.formato is FormatoItem.PROPOSICAO
    # Âncora + um cruzamento, uma vez só: o recuo e o crítico reusam os trechos.
    assert consultas == [ancora.texto, f"busca em profundidade\n{ancora.texto}"]
    assert "Articular com: busca em profundidade" in provedor.requisicoes[1].usuario
    assert _payload_da_geracao(db_session)["com_cruzamento"] is True
