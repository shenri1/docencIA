from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backend.app.domain import (
    EstadoBanco,
    EstadoQuestao,
    EstadoSessao,
    FaixaDificuldade,
    FormatoItem,
    NivelBloom,
    TipoQuestao,
)
from backend.app.exceptions import (
    BancoCongeladoException,
    FalhaProvedorLLMException,
    GeracaoEmAndamentoException,
    MaterialInsuficienteParaBancoException,
    ParametrosBancoDivergentesException,
    PromptDivergenteException,
    RespostaLLMInvalidaException,
)
from backend.app.models.banco import (
    Alternativa,
    AspectoEsperado,
    BancoQuestoes,
    FonteInterna,
    JustificativaEstruturada,
    Questao,
    RevisaoQuestao,
)
from backend.app.models.materiais import ChunkMaterial
from backend.app.prompt.parametros import ParametrosGeracao
from backend.app.services.geracao.banco_service import (
    Improdutiva,
    _montar_plano,
    _obter_ou_criar_banco,
    gerar_banco,
)
from backend.app.services.prompt_mestre_service import ativar, registrar_versao
from backend.tests.services.geracao.duplos import (
    CONTEXTO_MEDIA,
    ProvedorLLMFake,
    corpo_afirmativas,
    corpo_assercao,
    corpo_discursiva,
    corpo_discursiva_itens,
    corpo_insuficiencia,
    corpo_questao,
)
from backend.tests.services.rag.test_indexacao_service import criar_material

PARAMS_PROMPT = ParametrosGeracao(
    disciplina="Algoritmos",
    periodo="2026.2",
    area_do_conhecimento="Computação",
    tema_escopo="Grafos",
    k_alternativas=5,
    n_faceis=1,
    n_medias=2,
    n_dificeis=1,
)


def preparar(db, armazenamento, sessao, chunks: int = 20):
    """Prompt ativo, sessão confirmada e chunks suficientes para ancorar."""
    registrar_versao(db, "1.0.0", "docente", PARAMS_PROMPT)
    ativar(db, "1.0.0")
    material = criar_material(
        db, armazenamento, sessao, "P1", [("página 1", "conteúdo " * 40)]
    )
    db.query(ChunkMaterial).delete()
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
    sessao.estado = EstadoSessao.MATERIAIS_CONFIRMADOS
    db.commit()


def roteiro(n: int, k: int = 5) -> list[dict]:
    """Duas respostas por questão: rascunho do Gerador e revisão do crítico."""
    return [corpo_questao(k) for _ in range(2 * n)]


def corpo_do_item(item) -> dict:
    """O corpo que o modelo devolveria para este item do plano.
    Subtema distinto por número: a regra de sobreposição das provas
    compara subtema."""
    subtema = f"s{item.numero}"
    if item.formato is FormatoItem.AFIRMATIVAS:
        return corpo_afirmativas(item.configuracao, subtema=subtema)
    if item.formato is FormatoItem.ASSERCAO_RAZAO:
        return corpo_assercao(subtema=subtema)
    if item.n_itens is not None:
        return corpo_discursiva_itens(item.n_itens, subtema=subtema)
    if item.tipo is TipoQuestao.DISCURSIVA:
        return corpo_discursiva(subtema=subtema)
    return corpo_questao(5, subtema=subtema)


def roteiro_do_item(item) -> list[dict]:
    corpo = corpo_do_item(item)
    return [corpo, corpo]


def roteiro_do_plano(sessao, n_obj: int, n_disc: int = 0) -> list[dict]:
    """Duas respostas por questão, no formato que o plano atribui ao número."""
    roteiro_ = []
    for item in _montar_plano(sessao, n_obj, n_disc):
        corpo = corpo_do_item(item)
        roteiro_ += [corpo, corpo]
    return roteiro_


# `_montar_plano` só lê p_f, p_m, p_d e k_alternativas da sessão.
_SESSAO_PADRAO = SimpleNamespace(p_f=30, p_m=40, p_d=30, k_alternativas=5, p_calculo=0)


VARIACAO = "Que estrutura auxiliar garante a visita por camadas na busca em largura?"


def roteiro_variacao(n: int = 1, k: int = 5, enunciado: str = VARIACAO) -> list[dict]:
    """Como `roteiro`, com outro enunciado: a substituição recusa a candidata
    que repete a original, e `roteiro` repete sempre o mesmo enunciado."""
    return [corpo_questao(k, enunciado=enunciado) for _ in range(2 * n)]


def test_banco_respeita_a_distribuicao_por_faixa(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    # 10 questões com 30/40/30 -> 3 fáceis, 4 médias, 3 difíceis.
    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake(roteiro_misto(10, 0)),
        sessao_rascunho,
        n_objetivas=10,
        n_discursivas=0,
        versao="v1",
    )

    assert resumo.geradas == 10
    contagem = {
        faixa: db_session.query(Questao)
        .filter_by(banco_id=resumo.banco_id, faixa_dificuldade=faixa)
        .count()
        for faixa in FaixaDificuldade
    }
    assert contagem[FaixaDificuldade.FACIL] == 3
    assert contagem[FaixaDificuldade.MEDIA] == 4
    assert contagem[FaixaDificuldade.DIFICIL] == 3


def test_questao_persiste_com_alternativas_fontes_e_justificativa(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
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

    questao = db_session.query(Questao).filter_by(banco_id=resumo.banco_id).first()
    assert db_session.query(Alternativa).filter_by(questao_id=questao.id).count() == 5
    assert (
        db_session.query(Alternativa)
        .filter_by(questao_id=questao.id, correta=True)
        .count()
        == 1
    )
    assert db_session.query(FonteInterna).filter_by(questao_id=questao.id).count() >= 1
    justificativa = (
        db_session.query(JustificativaEstruturada)
        .filter_by(questao_id=questao.id)
        .one()
    )
    assert len(justificativa.invalidacao_distratores) == 4


def test_letras_sao_atribuidas_por_posicao_e_correta_segue_letra_correta(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake([corpo_questao(5, letra_correta="C")] * 2),
        sessao_rascunho,
        n_objetivas=1,
        n_discursivas=0,
        versao="v1",
    )

    questao = db_session.query(Questao).filter_by(banco_id=resumo.banco_id).one()
    alternativas = (
        db_session.query(Alternativa)
        .filter_by(questao_id=questao.id)
        .order_by(Alternativa.letra)
        .all()
    )
    assert [a.letra for a in alternativas] == ["A", "B", "C", "D", "E"]
    assert [a.texto for a in alternativas] == [
        f"Alternativa número {i} do teste" for i in range(5)
    ]
    assert [a.letra for a in alternativas if a.correta] == ["C"]
    assert [a.letra for a in alternativas if a.e_gemeo_malvado] == ["B"]


def test_insuficiencia_nao_aborta_o_banco(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    provedor = ProvedorLLMFake(
        [
            corpo_questao(5),
            corpo_questao(5),
            corpo_insuficiencia("faltou o critério"),
            corpo_questao(5),
            corpo_questao(5),
        ]
    )

    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        provedor,
        sessao_rascunho,
        n_objetivas=3,
        n_discursivas=0,
        versao="v1",
    )

    assert resumo.geradas == 2
    assert len(resumo.improdutivas) == 1
    assert "critério" in resumo.improdutivas[0].motivo
    assert resumo.improdutivas[0].numero == 2


def test_numeracao_e_sequencial_atraves_das_faixas(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """O plano concatena as faixas; a numeração tem que seguir contínua de 1 a
    n_alvo, sem repetir — `numero` é o índice da âncora e é unique por banco."""
    preparar(db_session, armazenamento, sessao_rascunho)
    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake(roteiro_misto(10, 0)),
        sessao_rascunho,
        n_objetivas=10,
        n_discursivas=0,
        versao="v1",
    )
    numeros = sorted(
        q.numero
        for q in db_session.query(Questao).filter_by(banco_id=resumo.banco_id).all()
    )
    assert numeros == list(range(1, 11))


def test_retomada_nao_regenera_o_que_ja_existe(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """Primeira chamada interrompida (roteiro acaba na questão 3), segunda
    continua com as MESMAS contagens e só gera o que falta."""
    preparar(db_session, armazenamento, sessao_rascunho)
    # O plano de 4 objetivas inclui formatos montados: o roteiro segue o plano.
    completo = roteiro_do_plano(sessao_rascunho, 4)
    interrompido = ProvedorLLMFake(completo[:4] + [RuntimeError("queda do Ollama")])
    with pytest.raises(RuntimeError):
        gerar_banco(
            db_session,
            embeddings_fake,
            reranker_fake,
            interrompido,
            sessao_rascunho,
            n_objetivas=4,
            n_discursivas=0,
            versao="v1",
        )

    segundo = ProvedorLLMFake(completo[4:])
    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        segundo,
        sessao_rascunho,
        n_objetivas=4,
        n_discursivas=0,
        versao="v1",
    )

    assert resumo.ja_existentes == 2
    assert resumo.geradas == 2
    assert segundo.chamadas == 4
    numeros = [
        q.numero
        for q in db_session.query(Questao).filter_by(banco_id=resumo.banco_id).all()
    ]
    assert sorted(numeros) == [1, 2, 3, 4]


def test_banco_congelado_falha_sem_chamar_o_modelo(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    banco = BancoQuestoes(
        sessao_id=sessao_rascunho.id,
        versao="v1",
        estado=EstadoBanco.CONGELADO,
        n_alvo=5,
        n_alvo_objetivas=5,
        n_alvo_discursivas=0,
        n_atual=0,
    )
    db_session.add(banco)
    db_session.commit()

    provedor = ProvedorLLMFake(roteiro(5))
    with pytest.raises(BancoCongeladoException):
        gerar_banco(
            db_session,
            embeddings_fake,
            reranker_fake,
            provedor,
            sessao_rascunho,
            n_objetivas=5,
            n_discursivas=0,
            versao="v1",
        )
    assert provedor.chamadas == 0


def test_material_insuficiente_falha_sem_chamar_o_modelo(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho, chunks=3)
    provedor = ProvedorLLMFake(roteiro(29))
    with pytest.raises(MaterialInsuficienteParaBancoException):
        gerar_banco(
            db_session,
            embeddings_fake,
            reranker_fake,
            provedor,
            sessao_rascunho,
            n_objetivas=29,
            n_discursivas=0,
            versao="v1",
        )
    assert provedor.chamadas == 0


def test_n_atual_reflete_o_que_foi_persistido(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    resumo = gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake(
            [
                corpo_questao(5),
                corpo_questao(5),
                corpo_insuficiencia(),
                corpo_questao(5),
                corpo_questao(5),
            ]
        ),
        sessao_rascunho,
        n_objetivas=3,
        n_discursivas=0,
        versao="v1",
    )
    banco = db_session.get(BancoQuestoes, resumo.banco_id)
    assert banco.n_atual == 2
    assert banco.n_alvo == 3
    assert (banco.n_alvo_objetivas, banco.n_alvo_discursivas) == (3, 0)


LONGA = "Opção com texto muito mais longo que todas as outras juntas somadas"


def alternativas(textos: list[str], gemeo: int = 1) -> list[dict]:
    return [{"texto": t, "e_gemeo_malvado": i == gemeo} for i, t in enumerate(textos)]


CURTAS = [f"Opção curta número {i}" for i in range(5)]
COM_LONGA = [CURTAS[0], CURTAS[1], LONGA, CURTAS[3], CURTAS[4]]


def gerar(db, emb, rer, sessao, provedor, n_alvo=1, n_discursivas=0):
    return gerar_banco(
        db,
        emb,
        rer,
        provedor,
        sessao,
        n_objetivas=n_alvo,
        n_discursivas=n_discursivas,
        versao="v1",
    )


def test_cada_questao_custa_duas_chamadas(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    provedor = ProvedorLLMFake(roteiro(3))
    resumo = gerar(
        db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor, 3
    )
    assert resumo.geradas == 3
    assert provedor.chamadas == 6


def test_revisao_persistida_com_rascunho_e_violacoes(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    rascunho = corpo_questao(
        5,
        contexto=CONTEXTO_MEDIA,
        enunciado="Rascunho?",
        alternativas=alternativas(COM_LONGA),
    )
    provedor = ProvedorLLMFake([rascunho, corpo_questao(5, contexto=CONTEXTO_MEDIA)])
    resumo = gerar(
        db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor
    )

    questao = db_session.query(Questao).filter_by(banco_id=resumo.banco_id).one()
    revisao = db_session.query(RevisaoQuestao).filter_by(questao_id=questao.id).one()
    assert revisao.rascunho["comando"] == "Rascunho?"
    assert [v["regra"] for v in revisao.violacoes_rascunho] == ["tamanho_alternativa"]
    assert revisao.violacoes_rascunho[0]["alvo"] == "C"
    assert revisao.violacoes_final == []
    assert revisao.modelo_geracao == "fake"
    assert revisao.modelo_revisao == "fake"
    # O que vai para Questao é a versão revisada.
    comando = corpo_questao(5)["resultado"]["comando"]
    assert questao.enunciado == f"{CONTEXTO_MEDIA}\n\n{comando}"
    assert resumo.com_violacoes == []


def test_violacoes_do_rascunho_chegam_ao_critico(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    rascunho = corpo_questao(5, alternativas=alternativas(COM_LONGA))
    provedor = ProvedorLLMFake([rascunho, corpo_questao(5)])
    gerar(db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor)
    assert "tamanho_alternativa" in provedor.requisicoes[1].usuario


def test_revisao_que_nao_corrige_mantem_a_violacao(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    ruim = corpo_questao(
        5, contexto=CONTEXTO_MEDIA, alternativas=alternativas(COM_LONGA)
    )
    resumo = gerar(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake([ruim, ruim]),
    )
    revisao = db_session.query(RevisaoQuestao).one()
    assert [v["regra"] for v in revisao.violacoes_final] == ["tamanho_alternativa"]
    assert [item.numero for item in resumo.com_violacoes] == [1]
    assert resumo.com_violacoes[0].violacoes[0].alvo == "C"


def test_fonte_persistida_vem_da_revisao_mesmo_com_rascunho_invalido(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """Só a revisada vira FonteInterna. Um P9 no rascunho que o crítico corrige
    não pode derrubar a questão."""
    preparar(db_session, armazenamento, sessao_rascunho)
    revisada = corpo_questao(
        5,
        fontes=[
            {
                "identificador_material": "P1",
                "localizacao": "página 77",
                "trecho_base": "Trecho citado pela revisão.",
            }
        ],
    )
    provedor = ProvedorLLMFake([corpo_questao(5, identificador="P9"), revisada])
    resumo = gerar(
        db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor
    )

    questao = db_session.query(Questao).filter_by(banco_id=resumo.banco_id).one()
    fonte = db_session.query(FonteInterna).filter_by(questao_id=questao.id).one()
    assert fonte.localizacao == "página 77"
    assert fonte.trecho_base == "Trecho citado pela revisão."


def test_fonte_inventada_na_revisao_vira_improdutiva_sem_persistir(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    provedor = ProvedorLLMFake([corpo_questao(5), corpo_questao(5, identificador="P9")])
    resumo = gerar(
        db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor
    )
    assert resumo.geradas == 0
    assert [i.numero for i in resumo.improdutivas] == [1]
    assert "P9" in resumo.improdutivas[0].motivo
    assert db_session.query(Questao).count() == 0
    assert db_session.query(RevisaoQuestao).count() == 0


def test_falha_de_conteudo_no_meio_nao_pára_o_banco(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    roteiro_ = [
        *roteiro(1),
        corpo_questao(5),
        corpo_questao(5, identificador="P9"),  # Q2: fonte inventada
        RespostaLLMInvalidaException("cortada"),  # Q3
        *roteiro(1),  # Q4
    ]
    provedor = ProvedorLLMFake(roteiro_)
    resumo = gerar(
        db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor, n_alvo=4
    )
    assert resumo.geradas == 2
    assert [i.numero for i in resumo.improdutivas] == [2, 3]
    assert resumo.restantes == 0
    assert sorted(q.numero for q in db_session.query(Questao)) == [1, 4]


def test_retomada_tenta_so_as_lacunas_da_falha(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    gerar(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake(
            [*roteiro(1), RespostaLLMInvalidaException("cortada"), *roteiro(1)]
        ),
        n_alvo=3,
    )
    provedor = ProvedorLLMFake(roteiro(1))
    resumo = gerar(
        db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor, n_alvo=3
    )
    assert resumo.geradas == 1
    assert provedor.chamadas == 2


def test_cadeia_de_provedores_fora_do_ar_continua_interrompendo(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    provedor = ProvedorLLMFake([FalhaProvedorLLMException([("ollama", "HTTP 500")])])
    with pytest.raises(FalhaProvedorLLMException):
        gerar(db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor)


def test_insuficiencia_declarada_pelo_critico_vira_improdutiva(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    provedor = ProvedorLLMFake(
        [corpo_questao(5), corpo_insuficiencia("o trecho não define o critério")]
    )
    resumo = gerar(
        db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor
    )
    assert resumo.geradas == 0
    assert resumo.improdutivas[0].motivo == "revisão: o trecho não define o critério"
    assert db_session.query(Questao).count() == 0


def test_ancora_recusada_pelo_critico_e_tentada_de_novo_na_retomada(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    gerar(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake([corpo_questao(5), corpo_insuficiencia()]),
    )
    resumo = gerar(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake(roteiro(1)),
    )
    assert resumo.ja_existentes == 0
    assert resumo.geradas == 1


def test_prompt_do_critico_editado_sem_versao_bloqueia_antes_do_modelo(
    db_session,
    armazenamento,
    embeddings_fake,
    reranker_fake,
    sessao_rascunho,
    monkeypatch,
):
    from backend.app.prompt import montagem
    from backend.app.services import prompt_mestre_service

    preparar(db_session, armazenamento, sessao_rascunho)
    monkeypatch.setattr(
        prompt_mestre_service,
        "carregar_modulos_versionados",
        lambda: [
            (nome, "editado" if nome == "critico/01_revisor.md" else conteudo)
            for nome, conteudo in montagem.carregar_modulos_versionados()
        ],
    )
    provedor = ProvedorLLMFake(roteiro(1))
    with pytest.raises(PromptDivergenteException):
        gerar(db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor)
    assert provedor.chamadas == 0


def test_bloom_da_objetiva_e_persistido_como_enum(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    gerar(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake(roteiro(1)),
    )
    db_session.expire_all()
    assert db_session.query(Questao).one().nivel_bloom is NivelBloom.APLICAR


def roteiro_misto(n_obj: int, n_disc: int) -> list[dict]:
    return roteiro_do_plano(_SESSAO_PADRAO, n_obj, n_disc)


def gerar_misto(db, emb, rer, sessao, provedor, n_obj, n_disc):
    return gerar_banco(
        db,
        emb,
        rer,
        provedor,
        sessao,
        n_objetivas=n_obj,
        n_discursivas=n_disc,
        versao="v1",
    )


def test_banco_misto_distribui_cada_tipo_e_numera_objetivas_primeiro(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    # 30/40/30: 10 objetivas -> 3/4/3; 5 discursivas -> 1/2/2 (maior resto,
    # desempate por dificuldade — calcular_distribuicao(5, 30, 40, 30)).
    resumo = gerar_misto(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake(roteiro_misto(10, 5)),
        10,
        5,
    )
    questoes = (
        db_session.query(Questao)
        .filter_by(banco_id=resumo.banco_id)
        .order_by(Questao.numero)
        .all()
    )
    assert [q.tipo for q in questoes] == [TipoQuestao.OBJETIVA] * 10 + [
        TipoQuestao.DISCURSIVA
    ] * 5

    def contagem(tipo):
        return [
            sum(1 for q in questoes if q.tipo is tipo and q.faixa_dificuldade is f)
            for f in FaixaDificuldade
        ]

    assert contagem(TipoQuestao.OBJETIVA) == [3, 4, 3]
    assert contagem(TipoQuestao.DISCURSIVA) == [1, 2, 2]
    assert resumo.geradas_por_tipo == {
        TipoQuestao.OBJETIVA: 10,
        TipoQuestao.DISCURSIVA: 5,
    }


def test_discursiva_persiste_aspectos_com_fonte_deduplicada(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """Review Focus 1: os dois aspectos do duplo citam a mesma fonte."""
    preparar(db_session, armazenamento, sessao_rascunho)
    resumo = gerar_misto(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake(roteiro_misto(0, 1)),
        0,
        1,
    )
    questao = db_session.query(Questao).filter_by(banco_id=resumo.banco_id).one()
    assert questao.tipo is TipoQuestao.DISCURSIVA
    assert questao.numero == 1
    assert db_session.query(Alternativa).filter_by(questao_id=questao.id).count() == 0

    fontes = db_session.query(FonteInterna).filter_by(questao_id=questao.id).all()
    assert len(fontes) == 1
    aspectos = (
        db_session.query(AspectoEsperado)
        .filter_by(questao_id=questao.id)
        .order_by(AspectoEsperado.ordem)
        .all()
    )
    assert [a.ordem for a in aspectos] == [1, 2]
    assert {a.fonte_interna_id for a in aspectos} == {fontes[0].id}

    justificativa = (
        db_session.query(JustificativaEstruturada)
        .filter_by(questao_id=questao.id)
        .one()
    )
    assert justificativa.objetivo_cognitivo == "explicar a estrutura auxiliar da busca"
    assert justificativa.justificativa_correta is None
    assert justificativa.invalidacao_distratores is None


def test_discursiva_pode_ser_criar(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    criar = corpo_discursiva(nivel_bloom="criar")
    gerar_misto(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake([criar, criar]),
        0,
        1,
    )
    assert db_session.query(Questao).one().nivel_bloom is NivelBloom.CRIAR


def test_aspecto_com_fonte_inventada_vira_improdutiva(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    provedor = ProvedorLLMFake(
        [corpo_discursiva(), corpo_discursiva(identificador="P9")]
    )
    resumo = gerar_misto(
        db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor, 0, 1
    )
    assert [i.numero for i in resumo.improdutivas] == [1]
    assert db_session.query(AspectoEsperado).count() == 0


def test_discursiva_e_validada_e_revisada_como_discursiva(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    sem_comando = corpo_discursiva(
        contexto=CONTEXTO_MEDIA, enunciado="Qual estrutura a busca em largura usa?"
    )
    provedor = ProvedorLLMFake([sem_comando, corpo_discursiva(contexto=CONTEXTO_MEDIA)])
    gerar_misto(
        db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor, 0, 1
    )
    assert "comando_ausente" in provedor.requisicoes[1].usuario
    assert "<revisao_discursiva>" in provedor.requisicoes[1].sistema
    revisao = db_session.query(RevisaoQuestao).one()
    assert [v["regra"] for v in revisao.violacoes_rascunho] == ["comando_ausente"]
    assert revisao.violacoes_final == []


def test_so_discursivas_comeca_em_q1(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """Review Focus 3: nenhum calcular_distribuicao(0, ...)."""
    preparar(db_session, armazenamento, sessao_rascunho)
    resumo = gerar_misto(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake(roteiro_misto(0, 3)),
        0,
        3,
    )
    assert resumo.geradas_por_tipo == {
        TipoQuestao.OBJETIVA: 0,
        TipoQuestao.DISCURSIVA: 3,
    }
    numeros = sorted(q.numero for q in db_session.query(Questao).all())
    assert numeros == [1, 2, 3]


def test_retomada_com_contagens_diferentes_e_409_sem_chamar_o_modelo(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    gerar_misto(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake(roteiro_misto(1, 1)),
        1,
        1,
    )
    provedor = ProvedorLLMFake(roteiro_misto(2, 0))
    with pytest.raises(ParametrosBancoDivergentesException):
        gerar_misto(
            db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor, 2, 0
        )
    assert provedor.chamadas == 0


def test_banco_anterior_a_10c_e_retomado_como_so_objetivas(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """Review Focus 2: banco criado antes da migração tem n_alvo_objetivas =
    n_alvo e n_alvo_discursivas = 0."""
    preparar(db_session, armazenamento, sessao_rascunho)
    db_session.add(
        BancoQuestoes(
            sessao_id=sessao_rascunho.id,
            versao="v1",
            n_alvo=2,
            n_alvo_objetivas=2,
            n_alvo_discursivas=0,
            n_atual=0,
        )
    )
    db_session.commit()
    resumo = gerar_misto(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake(roteiro(2)),
        2,
        0,
    )
    assert resumo.geradas == 2


def test_gerar_banco_move_a_sessao_para_banco_gerado(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    gerar(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake(roteiro(3)),
        n_alvo=3,
    )
    assert sessao_rascunho.estado is EstadoSessao.BANCO_GERADO


def test_retomada_continua_funcionando_com_a_sessao_em_banco_gerado(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """As guardas de índice e material testam `!= RASCUNHO`, então BANCO_GERADO
    não bloqueia a retomada."""
    preparar(db_session, armazenamento, sessao_rascunho)
    gerar(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake(roteiro(1) + [corpo_insuficiencia()]),
        n_alvo=2,
    )
    assert sessao_rascunho.estado is EstadoSessao.BANCO_GERADO
    resumo = gerar(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake(roteiro(1)),
        n_alvo=2,
    )
    assert resumo.geradas == 1
    assert resumo.ja_existentes == 1
    assert resumo.revisao == 0


def test_banco_nao_muda_de_estado_de_sessao_quando_nada_e_gerado(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    gerar(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake([corpo_insuficiencia()]),
        n_alvo=1,
    )
    assert sessao_rascunho.estado is EstadoSessao.MATERIAIS_CONFIRMADOS


def test_persistir_grava_subtema(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """`Questao.subtema` existia e nunca era escrito. A regra de
    sobreposição depende dele."""
    preparar(db_session, armazenamento, sessao_rascunho)
    gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake(roteiro(1)),
        sessao_rascunho,
        n_objetivas=1,
        n_discursivas=0,
        versao="v1",
    )
    questao = db_session.query(Questao).one()
    assert questao.subtema == "Busca em largura"


def test_persistir_grava_subtema_na_discursiva(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake([corpo_discursiva(), corpo_discursiva()]),
        sessao_rascunho,
        n_objetivas=0,
        n_discursivas=1,
        versao="v1",
    )
    questao = db_session.query(Questao).one()
    assert questao.subtema == "Busca em largura"


def test_persistir_grava_invalidacoes_com_letra_original(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """A letra gravada é a ORIGINAL; traduzir para a da prova é da leitura."""
    preparar(db_session, armazenamento, sessao_rascunho)
    gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorLLMFake(roteiro(1)),
        sessao_rascunho,
        n_objetivas=1,
        n_discursivas=0,
        versao="v1",
    )
    justificativa = db_session.query(JustificativaEstruturada).one()
    assert justificativa.invalidacao_distratores == [
        {"letra": "B", "motivo": "distrator 1"},
        {"letra": "C", "motivo": "distrator 2"},
        {"letra": "D", "motivo": "distrator 3"},
        {"letra": "E", "motivo": "distrator 4"},
    ]


# --- Achado 9: geração concorrente sobre o mesmo banco ---


def _outra_sessao(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def test_colisao_de_numero_com_outra_requisicao_responde_409_e_deixa_a_sessao_usavel(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho, engine
):
    """Retry do cliente após timeout: a 1ª requisição segue viva e grava a
    questão 1 enquanto esta ainda gera a sua. O índice parcial segura a
    corrupção; o que faltava era a colisão virar 409 em vez de 500."""
    preparar(db_session, armazenamento, sessao_rascunho)

    class ProvedorQueColide(ProvedorLLMFake):
        def gerar(self, sessao_id, requisicao):
            if self.chamadas == 0:
                with _outra_sessao(engine) as outra:
                    banco_da_outra = outra.scalar(select(BancoQuestoes))
                    outra.add(
                        Questao(
                            banco_id=banco_da_outra.id,
                            numero=1,
                            tipo=TipoQuestao.OBJETIVA,
                            formato=FormatoItem.PROPOSICAO,
                            enunciado="gravada pela outra requisição",
                            nivel_bloom=NivelBloom.APLICAR,
                            faixa_dificuldade=FaixaDificuldade.MEDIA,
                            tema="t",
                            subtema="s",
                            estado=EstadoQuestao.ATIVA,
                        )
                    )
                    outra.commit()
            return super().gerar(sessao_id, requisicao)

    with pytest.raises(GeracaoEmAndamentoException) as erro:
        gerar_banco(
            db_session,
            embeddings_fake,
            reranker_fake,
            ProvedorQueColide(roteiro(1)),
            sessao_rascunho,
            n_objetivas=1,
            n_discursivas=0,
            versao="v1",
        )

    assert erro.value.status_code == 409
    assert erro.value.extras["numero"] == 1
    # Rollback feito: a sessão continua utilizável e só a questão da outra existe.
    assert db_session.query(Questao).count() == 1


def test_criacao_concorrente_do_banco_reaproveita_o_que_a_outra_criou(
    db_session, sessao_rascunho, engine, monkeypatch
):
    """Duas requisições frias com a mesma `versao`: ambas leem "não existe" e a
    segunda esbarra em banco_por_sessao_versao no INSERT."""
    with _outra_sessao(engine) as outra:
        outra.add(
            BancoQuestoes(
                sessao_id=sessao_rascunho.id,
                versao="v1",
                n_alvo=1,
                n_alvo_objetivas=1,
                n_alvo_discursivas=0,
                n_atual=0,
            )
        )
        outra.commit()

    original = db_session.scalar
    leituras = []

    def primeira_leitura_nao_ve_o_banco(*args, **kwargs):
        leituras.append(1)
        return None if len(leituras) == 1 else original(*args, **kwargs)

    monkeypatch.setattr(db_session, "scalar", primeira_leitura_nao_ve_o_banco)

    banco = _obter_ou_criar_banco(db_session, sessao_rascunho, "v1", 1, 0)

    assert banco.versao == "v1"
    assert db_session.query(BancoQuestoes).count() == 1


def gerar_lote(db, emb, rer, sessao, provedor, apos=0, limite=None, n=4):
    return gerar_banco(
        db,
        emb,
        rer,
        provedor,
        sessao,
        n_objetivas=n,
        n_discursivas=0,
        versao="v1",
        apos=apos,
        limite=limite,
    )


def test_limite_tenta_so_n_numeros_e_diz_onde_parou(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    provedor = ProvedorLLMFake(roteiro_misto(4, 0))
    args = (db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor)

    r = gerar_lote(*args, limite=1)
    assert (r.geradas, r.ultimo_numero, r.restantes) == (1, 1, 3)
    r = gerar_lote(*args, apos=1, limite=2)
    assert (r.geradas, r.ultimo_numero, r.restantes) == (2, 3, 1)
    r = gerar_lote(*args, apos=3, limite=1)
    assert (r.geradas, r.ultimo_numero, r.restantes) == (1, 4, 0)
    assert provedor.chamadas == 8


def test_improdutiva_conta_como_tentada_e_o_apos_passa_por_cima(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    provedor = ProvedorLLMFake([corpo_insuficiencia()] + roteiro(1))
    args = (db_session, embeddings_fake, reranker_fake, sessao_rascunho, provedor)

    r = gerar_lote(*args, limite=1)
    assert (r.geradas, r.ultimo_numero, r.restantes) == (0, 1, 3)
    assert [i.numero for i in r.improdutivas] == [1]

    r = gerar_lote(*args, apos=1, limite=1)
    assert (r.geradas, r.ultimo_numero) == (1, 2)


def test_sem_limite_tenta_todos_e_termina_em_zero(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    r = gerar_lote(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake(roteiro_misto(4, 0)),
    )
    assert (r.geradas, r.ultimo_numero, r.restantes) == (4, 4, 0)


def test_lote_sem_pendentes_nao_tenta_nada(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    args = (db_session, embeddings_fake, reranker_fake, sessao_rascunho)
    gerar_lote(*args, ProvedorLLMFake(roteiro_misto(4, 0)))

    provedor = ProvedorLLMFake([])
    r = gerar_lote(*args, provedor, limite=1)
    assert (r.geradas, r.ultimo_numero, r.restantes) == (0, None, 0)
    assert provedor.chamadas == 0


def test_retomada_com_apos_zero_retenta_so_as_lacunas(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    args = (db_session, embeddings_fake, reranker_fake, sessao_rascunho)
    plano = _montar_plano(sessao_rascunho, 4, 0)
    # 1ª passada: o número 2 fica sem sustentação.
    gerar_lote(
        *args,
        ProvedorLLMFake(
            [
                *roteiro_do_item(plano[0]),
                corpo_insuficiencia(),
                *roteiro_do_item(plano[2]),
                *roteiro_do_item(plano[3]),
            ]
        ),
    )

    r = gerar_lote(*args, ProvedorLLMFake(roteiro_do_item(plano[1])), limite=1)
    assert (r.geradas, r.ultimo_numero, r.restantes) == (1, 2, 0)


def test_n_atual_nao_perde_incremento_de_outra_geracao(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho, engine
):
    """Duas gerações de números distintos: a outra grava a questão 2 e soma 1 a
    `n_atual` enquanto esta ainda gera a 1. `+= 1` em Python regravaria o valor
    lido antes (0 → 1) e o banco ficaria inconsistente."""
    preparar(db_session, armazenamento, sessao_rascunho)

    class ProvedorComOutraGeracao(ProvedorLLMFake):
        def gerar(self, sessao_id, requisicao):
            if self.chamadas == 0:
                with _outra_sessao(engine) as outra:
                    banco_da_outra = outra.scalar(select(BancoQuestoes))
                    outra.add(
                        Questao(
                            banco_id=banco_da_outra.id,
                            numero=2,
                            tipo=TipoQuestao.OBJETIVA,
                            formato=FormatoItem.PROPOSICAO,
                            enunciado="gravada pela outra geração",
                            nivel_bloom=NivelBloom.APLICAR,
                            faixa_dificuldade=FaixaDificuldade.MEDIA,
                            tema="t",
                            subtema="s",
                            estado=EstadoQuestao.ATIVA,
                        )
                    )
                    banco_da_outra.n_atual += 1
                    outra.commit()
            return super().gerar(sessao_id, requisicao)

    gerar_banco(
        db_session,
        embeddings_fake,
        reranker_fake,
        ProvedorComOutraGeracao(roteiro(1)),
        sessao_rascunho,
        n_objetivas=2,
        n_discursivas=0,
        versao="v1",
        limite=1,
    )

    db_session.expire_all()
    assert db_session.scalar(select(BancoQuestoes.n_atual)) == 2


# --- plano com formatos e itens, recuo, log ---


def test_plano_atribui_formato_por_faixa_e_e_estavel(sessao_rascunho):
    plano = _montar_plano(sessao_rascunho, 10, 0)  # 3 fáceis, 4 médias, 3 difíceis
    formatos = [(i.faixa.value, i.formato) for i in plano]
    assert formatos == [
        ("facil", FormatoItem.PROPOSICAO),
        ("facil", FormatoItem.PROPOSICAO),
        ("facil", FormatoItem.PROPOSICAO),
        ("media", FormatoItem.PROPOSICAO),
        ("media", FormatoItem.AFIRMATIVAS),
        ("media", FormatoItem.PROPOSICAO),
        ("media", FormatoItem.AFIRMATIVAS),
        ("dificil", FormatoItem.PROPOSICAO),
        ("dificil", FormatoItem.AFIRMATIVAS),
        ("dificil", FormatoItem.ASSERCAO_RAZAO),
    ]
    assert plano == _montar_plano(sessao_rascunho, 10, 0)
    afirmativas = [
        i.configuracao for i in plano if i.formato is FormatoItem.AFIRMATIVAS
    ]
    assert len(set(afirmativas)) == 3  # o rodízio corre entre faixas


def test_plano_da_discursiva_dificil_tem_itens(sessao_rascunho):
    plano = _montar_plano(sessao_rascunho, 0, 7)  # 2 fáceis, 3 médias, 2 difíceis
    assert [i.n_itens for i in plano] == [None, None, None, None, None, 2, 3]
    assert all(i.formato is FormatoItem.PROPOSICAO for i in plano)


def _gerar_um(db, emb, rer, sessao, item, roteiro_):
    from backend.app.services.geracao.ancoras import selecionar_ancoras
    from backend.app.services.geracao.banco_service import (
        _obter_ou_criar_banco,
        produzir_questao,
    )

    banco = _obter_ou_criar_banco(db, sessao, "v1", 10, 0)
    ancora = selecionar_ancoras(db, sessao, 10)[0]
    provedor = ProvedorLLMFake(roteiro_)
    return provedor, produzir_questao(
        db,
        emb,
        rer,
        provedor,
        sessao,
        banco,
        1,
        TipoQuestao.OBJETIVA,
        item["faixa"],
        ancora,
        item["distribuicao"],
        formato=item["formato"],
        configuracao=item["configuracao"],
    )


def test_afirmativas_persistem_formato_estrutura_e_correta_montada(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    cfg = (True, False, True)
    plano = _montar_plano(sessao_rascunho, 10, 0)
    item = {
        "faixa": plano[4].faixa,
        "distribuicao": plano[4].distribuicao,
        "formato": FormatoItem.AFIRMATIVAS,
        "configuracao": cfg,
    }
    provedor, produzida = _gerar_um(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        item,
        [corpo_afirmativas(cfg), corpo_afirmativas(cfg)],
    )
    questao = produzida.questao
    assert questao.formato is FormatoItem.AFIRMATIVAS
    correta = next(a for a in questao.alternativas if a.correta)
    assert correta.texto == "I e III, apenas."
    assert (
        questao.justificativa.estrutura_formato["afirmativas"][1]["verdadeira"] is False
    )
    assert "<formato_afirmativas>" in provedor.requisicoes[0].sistema
    assert "a afirmativa II deve ser falsa" in provedor.requisicoes[0].usuario


def test_insuficiencia_em_afirmativas_recua_para_proposicao_sem_nova_busca(
    db_session,
    armazenamento,
    embeddings_fake,
    reranker_fake,
    sessao_rascunho,
    monkeypatch,
):
    from backend.app.services.geracao import busca_orientada

    buscar = busca_orientada.buscar
    buscas = []

    def contar(*args, **kwargs):
        buscas.append(1)
        return buscar(*args, **kwargs)

    monkeypatch.setattr(busca_orientada, "buscar", contar)
    preparar(db_session, armazenamento, sessao_rascunho)
    plano = _montar_plano(sessao_rascunho, 10, 0)
    item = {
        "faixa": plano[4].faixa,
        "distribuicao": plano[4].distribuicao,
        "formato": FormatoItem.AFIRMATIVAS,
        "configuracao": (True, False, True),
    }
    provedor, produzida = _gerar_um(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        item,
        [
            corpo_insuficiencia(),
            corpo_questao(5, contexto=CONTEXTO_MEDIA),
            corpo_questao(5, contexto=CONTEXTO_MEDIA),
        ],
    )
    assert produzida.questao.formato is FormatoItem.PROPOSICAO
    assert provedor.chamadas == 3
    assert "<formato_proposicao>" in provedor.requisicoes[1].sistema
    # Embedding e as 20 chamadas de rerank, uma vez só: o recuo reusa os trechos.
    assert len(buscas) == 1


def test_insuficiencia_em_proposicao_nao_recua(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    plano = _montar_plano(sessao_rascunho, 10, 0)
    item = {
        "faixa": plano[0].faixa,
        "distribuicao": plano[0].distribuicao,
        "formato": FormatoItem.PROPOSICAO,
        "configuracao": None,
    }
    provedor, produzida = _gerar_um(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        item,
        [corpo_insuficiencia()],
    )
    assert isinstance(produzida, Improdutiva)
    assert provedor.chamadas == 1


def test_insuficiencia_do_critico_em_formato_montado_vira_improdutiva(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    cfg = (True, False, True)
    plano = _montar_plano(sessao_rascunho, 10, 0)
    item = {
        "faixa": plano[4].faixa,
        "distribuicao": plano[4].distribuicao,
        "formato": FormatoItem.AFIRMATIVAS,
        "configuracao": cfg,
    }
    provedor, produzida = _gerar_um(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        item,
        [corpo_afirmativas(cfg), corpo_insuficiencia()],
    )
    assert isinstance(produzida, Improdutiva)
    assert provedor.chamadas == 2


def test_log_da_geracao_tem_formato_planejado_e_gravado(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    from backend.app.domain import TipoEventoAuditoria
    from backend.app.models.auditoria import RegistroAuditoria

    preparar(db_session, armazenamento, sessao_rascunho)
    plano = _montar_plano(sessao_rascunho, 10, 0)
    item = {
        "faixa": plano[4].faixa,
        "distribuicao": plano[4].distribuicao,
        "formato": FormatoItem.AFIRMATIVAS,
        "configuracao": (True, False, True),
    }
    _gerar_um(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        item,
        [
            corpo_insuficiencia(),
            corpo_questao(5, contexto=CONTEXTO_MEDIA),
            corpo_questao(5, contexto=CONTEXTO_MEDIA),
        ],
    )
    payload = (
        db_session.query(RegistroAuditoria)
        .filter(
            RegistroAuditoria.tipo_evento == TipoEventoAuditoria.QUESTAO_GERADA.value
        )
        .one()
        .payload
    )
    assert payload["formato_planejado"] == "afirmativas"
    assert payload["formato"] == "proposicao"


def test_discursiva_dificil_persiste_aspectos_com_item(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    # 0 objetivas e 4 discursivas: 1 fácil, 2 médias, 1 difícil (Q4, 2 itens).
    roteiro_ = [corpo_discursiva(contexto=CONTEXTO_MEDIA)] * 6 + [
        corpo_discursiva_itens(2, contexto=" ".join(["palavra"] * 40))
    ] * 2
    gerar_misto(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        ProvedorLLMFake(roteiro_),
        0,
        4,
    )
    q4 = db_session.query(Questao).filter_by(numero=4).one()
    assert [(a.ordem, a.item) for a in q4.aspectos] == [(1, 1), (2, 2)]
    assert "a) " in q4.enunciado and "b) " in q4.enunciado


# --- plano com questões de cálculo ---


def test_plano_com_calculo_e_estavel(sessao_rascunho):
    sessao_rascunho.p_calculo = 40
    assert _montar_plano(sessao_rascunho, 10, 0) == _montar_plano(
        sessao_rascunho, 10, 0
    )


def test_plano_sem_calculo_nao_tem_formato_calculo(sessao_rascunho):
    plano = _montar_plano(sessao_rascunho, 10, 0)
    assert all(i.formato is not FormatoItem.CALCULO for i in plano)


def test_calculo_ocupa_posicoes_espalhadas(sessao_rascunho):
    sessao_rascunho.p_f, sessao_rascunho.p_m, sessao_rascunho.p_d = 100, 0, 0
    sessao_rascunho.p_calculo = 30
    plano = _montar_plano(sessao_rascunho, 10, 0)
    indices = {i for i, item in enumerate(plano) if item.formato is FormatoItem.CALCULO}
    assert indices == {0, 3, 6}


def test_rodizio_ignora_posicoes_de_calculo(sessao_rascunho):
    sessao_rascunho.p_f, sessao_rascunho.p_m, sessao_rascunho.p_d = 0, 100, 0
    sessao_rascunho.k_alternativas = 4
    sessao_rascunho.p_calculo = 50
    plano = _montar_plano(sessao_rascunho, 8, 0)
    outros = [i.formato for i in plano if i.formato is not FormatoItem.CALCULO]
    assert len(outros) == 4
    assert outros == [
        FormatoItem.PROPOSICAO,
        FormatoItem.AFIRMATIVAS,
        FormatoItem.PROPOSICAO,
        FormatoItem.AFIRMATIVAS,
    ]


def test_calculo_nao_conta_na_configuracao_das_afirmativas(sessao_rascunho):
    sessao_rascunho.p_f, sessao_rascunho.p_m, sessao_rascunho.p_d = 0, 100, 0
    sessao_rascunho.p_calculo = 50
    plano = _montar_plano(sessao_rascunho, 8, 0)
    assert all(
        i.configuracao is None for i in plano if i.formato is FormatoItem.CALCULO
    )


# --- formato CALCULO, violação de cálculo e recuo ---


def _item_calculo(sessao):
    plano = _montar_plano(sessao, 10, 0)
    return {
        "faixa": plano[4].faixa,  # média: CONTEXTO_MEDIA cobre o mínimo de palavras
        "distribuicao": plano[4].distribuicao,
        "formato": FormatoItem.CALCULO,
        "configuracao": None,
    }


def _payload_da_questao(db):
    from sqlalchemy import select as _select

    from backend.app.domain import TipoEventoAuditoria
    from backend.app.models.auditoria import RegistroAuditoria

    return db.scalars(
        _select(RegistroAuditoria.payload).where(
            RegistroAuditoria.tipo_evento == TipoEventoAuditoria.QUESTAO_GERADA.value
        )
    ).one()


def test_calculo_gera_com_alternativas_do_sistema(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    from backend.tests.services.geracao.duplos import corpo_calculo

    preparar(db_session, armazenamento, sessao_rascunho)
    provedor, produzida = _gerar_um(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        _item_calculo(sessao_rascunho),
        [corpo_calculo(), corpo_calculo()],
    )
    questao = produzida.questao
    assert questao.formato is FormatoItem.CALCULO
    assert provedor.chamadas == 2
    assert all(a.texto.startswith("\\(") for a in questao.alternativas)
    assert "Dados:" in questao.enunciado
    estrutura = questao.justificativa.estrutura_formato
    assert [d["simbolo"] for d in estrutura["dados"]] == ["g", "h"]
    assert estrutura["expressao"] == "sqrt(2 * g * h)"
    payload = _payload_da_questao(db_session)
    assert payload["formato_planejado"] == payload["formato"] == "calculo"
    assert payload["motivo_recuo"] is None
    assert payload["violacoes_recuo"] == []


def test_violacao_de_calculo_vai_ao_critico_e_e_corrigida(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    from backend.tests.services.geracao.duplos import corpo_calculo

    preparar(db_session, armazenamento, sessao_rascunho)
    provedor, produzida = _gerar_um(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        _item_calculo(sessao_rascunho),
        [corpo_calculo(expressao="__import__('os')"), corpo_calculo()],
    )
    questao = produzida.questao
    assert questao.formato is FormatoItem.CALCULO
    assert "[expressao_invalida] expressao" in provedor.requisicoes[1].usuario
    assert "expressao_invalida" in {
        v["regra"] for v in questao.revisao.violacoes_rascunho
    }
    assert _payload_da_questao(db_session)["motivo_recuo"] is None


def test_calculo_que_sobra_recua_para_proposicao_com_os_mesmos_trechos(
    db_session,
    armazenamento,
    embeddings_fake,
    reranker_fake,
    sessao_rascunho,
    monkeypatch,
    caplog,
):
    from backend.app.services.geracao import busca_orientada
    from backend.tests.services.geracao.duplos import corpo_calculo

    buscar = busca_orientada.buscar
    buscas = []

    def contar(*args, **kwargs):
        buscas.append(1)
        return buscar(*args, **kwargs)

    monkeypatch.setattr(busca_orientada, "buscar", contar)
    preparar(db_session, armazenamento, sessao_rascunho)
    invalido = corpo_calculo(expressao="__import__('os')")
    provedor, produzida = _gerar_um(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        _item_calculo(sessao_rascunho),
        [
            invalido,
            invalido,
            corpo_questao(5, contexto=CONTEXTO_MEDIA),
            corpo_questao(5, contexto=CONTEXTO_MEDIA),
        ],
    )
    assert produzida.questao.formato is FormatoItem.PROPOSICAO
    assert provedor.chamadas == 4
    assert "<formato_proposicao>" in provedor.requisicoes[2].sistema
    assert len(buscas) == 1
    payload = _payload_da_questao(db_session)
    assert payload["formato_planejado"] == "calculo"
    assert payload["formato"] == "proposicao"
    assert payload["motivo_recuo"] == "calculo"
    # A tentativa de cálculo não é persistida: o porquê fica no evento (só o
    # enum, ) e o detalhe no log da aplicação.
    assert payload["violacoes_recuo"] == ["expressao_invalida"]
    aviso = [r for r in caplog.records if "não montou" in r.getMessage()]
    assert len(aviso) == 1
    assert "expressao" in aviso[0].getMessage()


def test_insuficiencia_no_calculo_recua_com_motivo(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    provedor, produzida = _gerar_um(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        _item_calculo(sessao_rascunho),
        [
            corpo_insuficiencia("a fórmula"),
            corpo_questao(5, contexto=CONTEXTO_MEDIA),
            corpo_questao(5, contexto=CONTEXTO_MEDIA),
        ],
    )
    assert produzida.questao.formato is FormatoItem.PROPOSICAO
    payload = _payload_da_questao(db_session)
    assert payload["motivo_recuo"] == "insuficiencia"
    assert payload["violacoes_recuo"] == []


def test_insuficiencia_na_proposicao_apos_recuo_continua_improdutiva(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    preparar(db_session, armazenamento, sessao_rascunho)
    provedor, produzida = _gerar_um(
        db_session,
        embeddings_fake,
        reranker_fake,
        sessao_rascunho,
        _item_calculo(sessao_rascunho),
        [corpo_insuficiencia("a fórmula"), corpo_insuficiencia("o tema")],
    )
    assert isinstance(produzida, Improdutiva)
    assert provedor.chamadas == 2
    assert "o tema" in produzida.motivo
