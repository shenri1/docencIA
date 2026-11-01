import pytest
from sqlalchemy import select

from backend.app.domain import (
    DecisaoSubstituicao,
    EstadoBanco,
    EstadoProva,
    EstadoQuestao,
    EventoBanco,
    FaixaDificuldade,
    FormatoItem,
    TipoQuestao,
)
from backend.app.exceptions import (
    CandidataPendenteException,
    EstadoQuestaoInvalidoException,
    QuestaoNaoEncontradaException,
    RevisaoDesatualizadaException,
    SemCandidataPendenteException,
    SubstituicaoAposMontagemException,
)
from backend.app.models.banco import BancoQuestoes, Questao, RegistroSubstituicao
from backend.app.models.provas import Prova
from backend.app.services.controle_banco import substituicao_service
from backend.app.services.controle_banco.exclusao_service import (
    congelar_banco,
    excluir_questoes,
)
from backend.app.services.controle_banco.substituicao_service import (
    aceitar_substituicao,
    propor_substituicao,
    rejeitar_substituicao,
)
from backend.app.services.geracao.banco_service import (
    Improdutiva,
    _montar_plano,
    gerar_banco,
)
from backend.tests.services.geracao.duplos import (
    CONTEXTO_MEDIA,
    ProvedorLLMFake,
    corpo_afirmativas,
    corpo_discursiva,
    corpo_insuficiencia,
    corpo_questao,
)
from backend.tests.services.geracao.test_banco_service import (
    VARIACAO,
    preparar,
    roteiro,
    roteiro_do_plano,
    roteiro_variacao,
)
from backend.tests.travamento import espiar_lock


def banco_gerado(db, armazenamento, embeddings, reranker, sessao, n=3):
    """Banco real, pelo laço de geração e revisão: a substituição precisa das âncoras
    determinísticas, que só existem sobre material indexado."""
    preparar(db, armazenamento, sessao)
    resumo = gerar_banco(
        db,
        embeddings,
        reranker,
        ProvedorLLMFake(roteiro(n)),
        sessao,
        n_objetivas=n,
        n_discursivas=0,
        versao="v1",
    )
    return db.get(BancoQuestoes, resumo.banco_id)


def _propor(db, emb, rer, docente, banco, numero, roteiro_=None):
    return propor_substituicao(
        db,
        emb,
        rer,
        ProvedorLLMFake(roteiro_ or roteiro_variacao(1)),
        docente,
        banco,
        numero,
    )


def test_propor_nao_altera_o_banco(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    revisao_antes, n_antes = banco.revisao, banco.n_atual
    original = next(q for q in banco.questoes if q.numero == 2)

    produzida = _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 2)

    assert produzida.questao.estado is EstadoQuestao.CANDIDATA
    assert produzida.questao.numero == 2
    assert produzida.questao.tipo is TipoQuestao.OBJETIVA
    assert original.estado is EstadoQuestao.ATIVA
    assert (banco.revisao, banco.n_atual) == (revisao_antes, n_antes)


def test_propor_manda_o_enunciado_da_original_como_evitar(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    original = next(q for q in banco.questoes if q.numero == 1)
    provedor = ProvedorLLMFake(roteiro_variacao(1))

    propor_substituicao(
        db_session, embeddings_fake, reranker_fake, provedor, docente, banco, 1
    )

    usuario = provedor.requisicoes[0].usuario
    assert original.enunciado in usuario
    # Objetiva manda também as alternativas: o docente não quer a mesma questão
    # com as mesmas opções em outra ordem.
    assert original.alternativas[0].texto in usuario


def test_aceitar_troca_no_mesmo_numero_e_preserva_a_original(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    original = next(q for q in banco.questoes if q.numero == 2)
    candidata = _propor(
        db_session, embeddings_fake, reranker_fake, docente, banco, 2
    ).questao

    relatorio = aceitar_substituicao(db_session, docente, banco, 2, banco.revisao)

    assert original.estado is EstadoQuestao.SUBSTITUIDA
    assert candidata.estado is EstadoQuestao.ATIVA
    assert candidata.numero == 2
    assert banco.n_atual == 3  # a original já era ativa: a contagem não muda
    assert relatorio.evento is EventoBanco.SUBSTITUICAO
    assert banco.revisao == relatorio.revisao
    registro = db_session.query(RegistroSubstituicao).one()
    assert registro.decisao is DecisaoSubstituicao.ACEITA
    assert (registro.questao_original_id, registro.candidata_id) == (
        original.id,
        candidata.id,
    )


def test_aceitar_substituicao_de_questao_excluida_recoloca_no_banco(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """ "Excluí a Q2 e agora quero outra no lugar" é o reequilíbrio manual."""
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    excluir_questoes(db_session, docente, banco, [2], banco.revisao)
    assert banco.n_atual == 2

    _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 2)
    aceitar_substituicao(db_session, docente, banco, 2, banco.revisao)
    assert banco.n_atual == 3


def test_rejeitar_descarta_sem_mexer_no_banco(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    revisao_antes = banco.revisao
    produzida = _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 3)

    descartada = rejeitar_substituicao(db_session, docente, banco, 3)

    assert descartada.id == produzida.questao.id
    assert descartada.estado is EstadoQuestao.DESCARTADA
    assert banco.revisao == revisao_antes
    assert db_session.query(RegistroSubstituicao).one().decisao is (
        DecisaoSubstituicao.REJEITADA
    )


def test_depois_de_rejeitar_pode_propor_de_novo(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)
    rejeitar_substituicao(db_session, docente, banco, 1)
    segunda = _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)
    assert segunda.questao.estado is EstadoQuestao.CANDIDATA


def test_propor_com_candidata_pendente_responde_409(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)
    with pytest.raises(CandidataPendenteException):
        _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)


def test_propor_numero_inexistente_responde_404(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    with pytest.raises(QuestaoNaoEncontradaException):
        _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 99)


def test_propor_substituicao_de_questao_substituida_responde_409(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)
    aceitar_substituicao(db_session, docente, banco, 1, banco.revisao)
    # A original agora é SUBSTITUIDA. Propor de novo atinge a ATIVA nova, o que
    # é permitido; o que não pode é mirar a linha substituída.
    substituida = db_session.scalars(
        select(Questao).where(
            Questao.banco_id == banco.id,
            Questao.estado == EstadoQuestao.SUBSTITUIDA,
        )
    ).one()
    substituida.numero = 98
    db_session.commit()
    with pytest.raises(EstadoQuestaoInvalidoException):
        _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 98)


def test_insuficiencia_na_proposta_nao_persiste_nada(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    antes = db_session.query(Questao).count()
    resultado = _propor(
        db_session,
        embeddings_fake,
        reranker_fake,
        docente,
        banco,
        1,
        [corpo_insuficiencia("o trecho não sustenta outra questão")],
    )
    assert isinstance(resultado, Improdutiva)
    assert db_session.query(Questao).count() == antes


def test_candidata_que_repete_a_original_e_gerada_de_novo(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """Medido: o qwen3:4b, com a mesma âncora, devolveu o enunciado da original
    palavra por palavra, apesar do "não a repita" no prompt."""
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    original = next(q for q in banco.questoes if q.numero == 1)
    # Caixa e pontuação não disfarçam a cópia.
    copia = corpo_questao(5, enunciado=original.enunciado.upper() + "!")
    provedor = ProvedorLLMFake([copia, *roteiro_variacao(1)])

    produzida = propor_substituicao(
        db_session, embeddings_fake, reranker_fake, provedor, docente, banco, 1
    )

    assert produzida.questao.enunciado == VARIACAO
    # Rascunho repetido, novo rascunho, revisão: a cópia não gasta o crítico.
    assert provedor.chamadas == 3
    assert "repetiu" in provedor.requisicoes[1].usuario


def test_candidata_que_repete_duas_vezes_vira_insuficiencia(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    antes = db_session.query(Questao).count()
    provedor = ProvedorLLMFake(roteiro(1))  # o mesmo enunciado da original, 2x

    resultado = propor_substituicao(
        db_session, embeddings_fake, reranker_fake, provedor, docente, banco, 1
    )

    assert isinstance(resultado, Improdutiva)
    assert "variação diferente da original" in resultado.motivo
    assert provedor.chamadas == 2
    assert db_session.query(Questao).count() == antes


def test_discursiva_manda_os_aspectos_como_evitar(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake([corpo_discursiva()] * 2),
        sessao_rascunho,
        n_objetivas=0,
        n_discursivas=1,
        versao="v1",
    )
    banco = db_session.get(BancoQuestoes, resumo.banco_id)
    outra = corpo_discursiva(
        enunciado="Compare a fila da busca em largura com a pilha da busca em profundidade."
    )
    provedor = ProvedorLLMFake([outra] * 2)

    propor_substituicao(
        db_session, embeddings_fake, reranker_fake, provedor, docente, banco, 1
    )

    assert "a fila preserva a ordem de descoberta" in provedor.requisicoes[0].usuario


def test_aceitar_sem_candidata_responde_409(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    with pytest.raises(SemCandidataPendenteException):
        aceitar_substituicao(db_session, docente, banco, 1, banco.revisao)


def test_rejeitar_sem_candidata_responde_409(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    with pytest.raises(SemCandidataPendenteException):
        rejeitar_substituicao(db_session, docente, banco, 1)


def test_aceitar_com_revisao_desatualizada_responde_409(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)
    with pytest.raises(RevisaoDesatualizadaException):
        aceitar_substituicao(db_session, docente, banco, 1, banco.revisao + 5)


def test_substituicao_funciona_com_banco_congelado(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """O congelamento fecha a janela de exclusões, não a substituição
    com comando explícito. É por aqui que as propostas da auditoria (
    parte B) viram ação."""
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    congelar_banco(db_session, docente, banco, banco.revisao)
    assert banco.estado is EstadoBanco.CONGELADO

    _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)
    relatorio = aceitar_substituicao(db_session, docente, banco, 1, banco.revisao)
    assert relatorio.evento is EventoBanco.SUBSTITUICAO
    assert banco.estado is EstadoBanco.CONGELADO


def test_candidata_usa_a_mesma_faixa_da_original(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    original = next(q for q in banco.questoes if q.numero == 3)
    produzida = _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 3)
    assert produzida.questao.faixa_dificuldade is original.faixa_dificuldade
    assert isinstance(original.faixa_dificuldade, FaixaDificuldade)


def test_duas_substituicoes_do_mesmo_numero(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """Duas SUBSTITUIDA no número 1 é o caso normal, e é por isso que o índice
    é parcial em vez de UniqueConstraint(banco_id, numero)."""
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    # Cada variação precisa diferir da questão que está no número naquele momento.
    for enunciado in (VARIACAO, "Por que a fila preserva a ordem de descoberta?"):
        _propor(
            db_session,
            embeddings_fake,
            reranker_fake,
            docente,
            banco,
            1,
            roteiro_variacao(1, enunciado=enunciado),
        )
        aceitar_substituicao(db_session, docente, banco, 1, banco.revisao)

    do_numero_1 = [q for q in banco.questoes if q.numero == 1]
    estados = sorted(q.estado.value for q in do_numero_1)
    assert estados == ["ativa", "substituida", "substituida"]
    assert banco.n_atual == 3


def test_aceitar_com_provas_montadas_responde_409_e_nao_muda_nada(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """Achado 5: aceitar move a revisão do banco; as provas já montadas ficam
    na revisão antiga, a exportação bloqueia para sempre e remontar não existe."""
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    produzida = _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)
    congelar_banco(db_session, docente, banco, banco.revisao)
    db_session.add(
        Prova(
            sessao_id=banco.sessao_id,
            banco_id=banco.id,
            versao="A",
            n_questoes=3,
            n_objetivas=3,
            n_discursivas=0,
            revisao_banco=banco.revisao,
            estado=EstadoProva.MONTADA,
        )
    )
    db_session.commit()
    revisao_antes = banco.revisao

    with pytest.raises(SubstituicaoAposMontagemException) as erro:
        aceitar_substituicao(db_session, docente, banco, 1, banco.revisao)

    assert erro.value.status_code == 409
    assert banco.revisao == revisao_antes
    assert produzida.questao.estado is EstadoQuestao.CANDIDATA


def test_aceitar_segura_o_lock_da_linha_do_banco(
    db_session,
    docente,
    armazenamento,
    embeddings_fake,
    reranker_fake,
    sessao_rascunho,
    engine,
    monkeypatch,
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    _propor(db_session, embeddings_fake, reranker_fake, docente, banco, 1)
    achados = espiar_lock(
        monkeypatch, substituicao_service, "registrar_relatorio", engine, banco.id
    )

    aceitar_substituicao(db_session, docente, banco, 1, banco.revisao)

    assert achados == [False]


# --- ---


def test_substituicao_de_questao_anterior_a_etapa_18(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    original = next(q for q in banco.questoes if q.numero == 1)
    original.justificativa.estrutura_formato = None  # como antes da etapa
    db_session.commit()
    copia = corpo_questao(5, enunciado=original.enunciado)
    provedor = ProvedorLLMFake([copia, *roteiro_variacao(1)])
    produzida = propor_substituicao(
        db_session, embeddings_fake, reranker_fake, provedor, docente, banco, 1
    )
    assert produzida.questao.enunciado == VARIACAO
    assert produzida.questao.formato is FormatoItem.PROPOSICAO


def test_variacao_que_reusa_o_cenario_nao_e_copia(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    cenario = " ".join(["cenário"] * 40)
    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake([corpo_questao(5, contexto=cenario)] * 2),
        sessao_rascunho,
        n_objetivas=1,
        n_discursivas=0,
        versao="v1",
    )
    banco = db_session.get(BancoQuestoes, resumo.banco_id)
    outra = corpo_questao(5, contexto=cenario, enunciado=VARIACAO)
    provedor = ProvedorLLMFake([outra, outra])
    produzida = propor_substituicao(
        db_session, embeddings_fake, reranker_fake, provedor, docente, banco, 1
    )
    assert provedor.chamadas == 2  # nenhuma recusa por cópia
    assert produzida.questao.enunciado.endswith(VARIACAO)


def _banco_com_afirmativas(db, armazenamento, emb, rer, sessao):
    """Banco de 4 objetivas gerado pelo laço; devolve o número que o plano pôs
    em AFIRMATIVAS e a configuração dele."""
    preparar(db, armazenamento, sessao)
    numero, cfg = next(
        (i.numero, i.configuracao)
        for i in _montar_plano(sessao, 4, 0)
        if i.formato is FormatoItem.AFIRMATIVAS
    )
    resumo = gerar_banco(
        db,
        emb,
        rer,
        ProvedorLLMFake(roteiro_do_plano(sessao, 4)),
        sessao,
        n_objetivas=4,
        n_discursivas=0,
        versao="v1",
    )
    return db.get(BancoQuestoes, resumo.banco_id), numero, cfg


def test_substituicao_mantem_formato_e_configuracao(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco, numero, cfg = _banco_com_afirmativas(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    outras = (
        "A fila guarda os descobertos.",
        "A pilha guarda os descobertos.",
        "A visita segue camadas de distância.",
    )
    provedor = ProvedorLLMFake([corpo_afirmativas(cfg, textos=outras)] * 2)
    produzida = propor_substituicao(
        db_session, embeddings_fake, reranker_fake, provedor, docente, banco, numero
    )
    assert produzida.questao.formato is FormatoItem.AFIRMATIVAS
    estrutura = produzida.questao.justificativa.estrutura_formato
    assert tuple(a["verdadeira"] for a in estrutura["afirmativas"]) == cfg


def test_substituicao_de_afirmativas_recua_para_proposicao(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco, numero, cfg = _banco_com_afirmativas(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    variacao = corpo_questao(5, contexto=CONTEXTO_MEDIA, enunciado=VARIACAO)
    provedor = ProvedorLLMFake([corpo_insuficiencia(), variacao, variacao])
    produzida = propor_substituicao(
        db_session, embeddings_fake, reranker_fake, provedor, docente, banco, numero
    )
    assert (
        "a afirmativa" in provedor.requisicoes[0].usuario
    )  # tentou o formato da original
    assert produzida.questao.formato is FormatoItem.PROPOSICAO
    original = next(
        q for q in banco.questoes if q.numero == numero and q.estado.value == "ativa"
    )
    assert original.formato is FormatoItem.AFIRMATIVAS
    assert (
        tuple(
            a["verdadeira"]
            for a in original.justificativa.estrutura_formato["afirmativas"]
        )
        == cfg
    )


from backend.app.domain import EstadoOrientacao, OrigemOrientacao
from backend.app.exceptions import LimiteOrientacoesException
from backend.app.models.orientacoes import OrientacaoDocente
from backend.app.schemas.orientacao import DirecaoVariacao
from backend.app.services.orientacoes.orientacao_service import (
    criar_orientacao_sessao,
    vigentes,
)


def _guiada(db, emb, rer, docente, banco, numero, direcao, roteiro_):
    provedor = ProvedorLLMFake(roteiro_)
    produzida = propor_substituicao(
        db, emb, rer, provedor, docente, banco, numero, direcao
    )
    return provedor, produzida


def test_variacao_guiada_grava_pontual_e_liga_a_candidata(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    provedor, produzida = _guiada(
        db_session,
        embeddings_fake,
        reranker_fake,
        docente,
        banco,
        1,
        DirecaoVariacao(o_que_mudar="use um exemplo de rede"),
        roteiro_variacao(1),
    )

    [orientacao] = produzida.questao.orientacoes
    assert orientacao.estado is EstadoOrientacao.PONTUAL
    assert orientacao.origem is OrigemOrientacao.QUESTAO
    assert (orientacao.banco_id, orientacao.numero_origem) == (banco.id, 1)
    usuario = provedor.requisicoes[0].usuario
    assert "Orientações do docente:\n1. Mudar: use um exemplo de rede" in usuario
    assert "Questão de partida" in usuario
    assert "não a repita" not in usuario
    # A pontual não entra em outra geração.
    assert vigentes(db_session, sessao_rascunho) == []


def test_variacao_acumulada_vira_vigente(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    _, produzida = _guiada(
        db_session,
        embeddings_fake,
        reranker_fake,
        docente,
        banco,
        1,
        DirecaoVariacao(cruzar_com="busca em profundidade", acumular=True),
        roteiro_variacao(1),
    )

    [orientacao] = produzida.questao.orientacoes
    assert orientacao.estado is EstadoOrientacao.ATIVA
    assert [o.id for o in vigentes(db_session, sessao_rascunho)] == [orientacao.id]


def test_vigentes_vem_antes_da_orientacao_da_variacao(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    criar_orientacao_sessao(db_session, docente, sessao_rascunho, "enunciados curtos")
    provedor, _ = _guiada(
        db_session,
        embeddings_fake,
        reranker_fake,
        docente,
        banco,
        1,
        DirecaoVariacao(o_que_mudar="use um exemplo de rede"),
        roteiro_variacao(1),
    )
    assert (
        "1. Mudar: enunciados curtos\n2. Mudar: use um exemplo de rede"
        in provedor.requisicoes[0].usuario
    )


def test_sem_direcao_manda_as_vigentes_e_o_nao_repita(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    criar_orientacao_sessao(db_session, docente, sessao_rascunho, "enunciados curtos")
    provedor = ProvedorLLMFake(roteiro_variacao(1))
    propor_substituicao(
        db_session, embeddings_fake, reranker_fake, provedor, docente, banco, 1
    )
    usuario = provedor.requisicoes[0].usuario
    assert "1. Mudar: enunciados curtos" in usuario
    assert "não a repita" in usuario


def test_insuficiencia_mantem_a_orientacao_gravada(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    _, produzida = _guiada(
        db_session,
        embeddings_fake,
        reranker_fake,
        docente,
        banco,
        1,
        DirecaoVariacao(cruzar_com="redes de computadores"),
        # Duas: se a original não for proposição, o recuo pede de novo.
        [
            corpo_insuficiencia(
                "o material não sustenta a relação com redes de computadores"
            )
        ]
        * 2,
    )

    assert isinstance(produzida, Improdutiva)
    assert "redes de computadores" in produzida.motivo
    orientacao = db_session.scalars(select(OrientacaoDocente)).one()
    assert orientacao.cruzar_com == "redes de computadores"
    assert not db_session.scalars(
        select(Questao).where(Questao.estado == EstadoQuestao.CANDIDATA)
    ).all()


def test_teto_estourado_nao_chama_o_provedor(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    for i in range(5):
        criar_orientacao_sessao(db_session, docente, sessao_rascunho, f"orientação {i}")
    provedor = ProvedorLLMFake([])

    with pytest.raises(LimiteOrientacoesException):
        propor_substituicao(
            db_session,
            embeddings_fake,
            reranker_fake,
            provedor,
            docente,
            banco,
            1,
            DirecaoVariacao(o_que_mudar="mais uma", acumular=True),
        )
    assert provedor.chamadas == 0


def test_variacao_guiada_mantem_formato_da_original(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    original = next(q for q in banco.questoes if q.numero == 1)
    _, produzida = _guiada(
        db_session,
        embeddings_fake,
        reranker_fake,
        docente,
        banco,
        1,
        DirecaoVariacao(o_que_mudar="enunciado mais curto"),
        roteiro_variacao(1),
    )
    assert produzida.questao.formato is original.formato
    assert produzida.questao.faixa_dificuldade is original.faixa_dificuldade


def test_copia_na_variacao_guiada_ganha_nova_tentativa(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """A detecção de cópia continua valendo com a questão de partida."""
    banco = banco_gerado(
        db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
    )
    provedor, produzida = _guiada(
        db_session,
        embeddings_fake,
        reranker_fake,
        docente,
        banco,
        1,
        DirecaoVariacao(o_que_mudar="enunciado mais curto"),
        [corpo_questao(5)] + roteiro_variacao(1),
    )
    assert produzida.questao is not None
    segunda = provedor.requisicoes[1].usuario
    assert "Questão de partida" in segunda
    assert substituicao_service._AVISO_REPETICAO in segunda


def test_substituicao_mantem_calculo_e_recalcula(
    db_session, docente, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    from backend.tests.services.geracao.duplos import corpo_calculo

    preparar(db_session, armazenamento, sessao_rascunho)
    sessao_rascunho.p_calculo = 100
    db_session.commit()
    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake([corpo_calculo(), corpo_calculo()]),
        sessao_rascunho,
        n_objetivas=1,
        n_discursivas=0,
        versao="v1",
    )
    banco = db_session.get(BancoQuestoes, resumo.banco_id)
    original = next(q for q in banco.questoes if q.numero == 1)
    assert original.formato is FormatoItem.CALCULO

    outra = corpo_calculo(
        comando="Com que rapidez o corpo atinge o chão nesse novo cenário?",
        dados=[
            {"simbolo": "g", "valor": 9.81, "unidade": "m/s**2"},
            {"simbolo": "h", "valor": 8, "unidade": "m"},
        ],
    )
    provedor = ProvedorLLMFake([outra, outra])
    produzida = propor_substituicao(
        db_session, embeddings_fake, reranker_fake, provedor, docente, banco, 1
    )
    candidata = produzida.questao
    assert candidata.formato is FormatoItem.CALCULO
    assert candidata.justificativa.estrutura_formato["dados"][1]["valor"] == 8
    assert {a.texto for a in candidata.alternativas} != {
        a.texto for a in original.alternativas
    }
