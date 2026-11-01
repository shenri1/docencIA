from backend.app.domain import EstadoSessao, FaixaDificuldade, TipoQuestao
from backend.app.services.calculo_distribuicao_service import calcular_distribuicao
from backend.app.services.geracao.agente_gerador_service import gerar_questao
from backend.app.services.rag.chunking import ConfigChunking
from backend.app.services.rag.indexacao_service import indexar_sessao
from backend.tests.services.geracao.duplos import (
    ProvedorLLMFake,
    corpo_discursiva,
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
    assert resultado.questao.nivel_bloom == "aplicar"
    assert len(resultado.questao.alternativas) == sessao_rascunho.k_alternativas
    # Os trechos enviados voltam no resultado: o crítico precisa ver o mesmo
    # material, e as fontes só são resolvidas depois da revisão.
    assert [t.identificador_curto for t in resultado.trechos] == ["P1"] * len(
        resultado.trechos
    )
    assert resultado.trechos
    assert resultado.modelo == "fake"


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


def test_schema_so_aceita_fonte_dos_trechos_enviados(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """O identificador da fonte é enum dos trechos desta chamada: com o
    qwen2.5:3b, "P1, página 10" e materiais que não vieram derrubavam a questão
    em `resolver_fontes`. Agora a decodificação restrita não os produz."""
    import pytest
    from pydantic import ValidationError

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
    esquema = provedor.requisicoes[0].formato
    enviados = {t.identificador_curto for t in resultado.trechos}
    esquema.model_validate(corpo_questao(sessao_rascunho.k_alternativas))
    with pytest.raises(ValidationError):
        esquema.model_validate(
            corpo_questao(sessao_rascunho.k_alternativas, identificador="P9")
        )
    assert "P9" not in enviados


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


def test_discursiva_usa_schema_sistema_e_pedido_proprios(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    ancora = preparar(db_session, armazenamento, embeddings_fake, sessao_rascunho)
    provedor = ProvedorLLMFake([corpo_discursiva()])
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
        tipo=TipoQuestao.DISCURSIVA,
    )
    requisicao = provedor.requisicoes[0]
    assert "<formato_discursiva>" in requisicao.sistema
    assert "<qualidade_alternativas>" not in requisicao.sistema
    assert "discursiva" in requisicao.usuario
    assert "2 a 5 aspectos esperados" in requisicao.usuario
    assert "alternativas" not in requisicao.usuario
    assert len(resultado.questao.aspectos_esperados) == 2


def test_objetiva_continua_o_default(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    ancora = preparar(db_session, armazenamento, embeddings_fake, sessao_rascunho)
    provedor = ProvedorLLMFake([corpo_questao(sessao_rascunho.k_alternativas)])
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
    assert "<formato_objetiva>" in provedor.requisicoes[0].sistema


def test_evitar_entra_na_mensagem_de_usuario(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    """A substituição pede ao Gerador para não repetir a original. Muda a
    mensagem de usuário, não o prompt mestre — logo, não exige versão nova."""
    ancora = preparar(db_session, armazenamento, embeddings_fake, sessao_rascunho)
    provedor = ProvedorLLMFake([corpo_questao(sessao_rascunho.k_alternativas)])

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
        evitar="Q4: Qual estrutura a busca em profundidade usa?",
    )

    usuario = provedor.requisicoes[0].usuario
    assert "não a repita" in usuario
    assert "Qual estrutura a busca em profundidade usa?" in usuario


def test_sem_evitar_a_mensagem_nao_muda(
    db_session, armazenamento, embeddings_fake, reranker_fake, sessao_rascunho
):
    ancora = preparar(db_session, armazenamento, embeddings_fake, sessao_rascunho)
    provedor = ProvedorLLMFake([corpo_questao(sessao_rascunho.k_alternativas)])
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
    assert "não a repita" not in provedor.requisicoes[0].usuario


from types import SimpleNamespace as _NS

from backend.app.domain import FaixaDificuldade as _Faixa
from backend.app.domain import FormatoItem as _Formato
from backend.app.domain import TipoQuestao as _Tipo
from backend.app.services.geracao.agente_gerador_service import (
    _montar_usuario as _usuario_gerador,
)
from backend.app.services.geracao.contexto import formatar_trechos as _formatar_trechos
from backend.app.services.geracao.formatos import (
    texto_contextualizacao as _contextualizacao,
)
from backend.app.services.geracao.formatos import (
    texto_pedido_formato as _pedido_formato,
)
from backend.app.services.rag.retrieval_service import TrechoRecuperado as _Trecho

_TRECHOS = [
    _Trecho(
        chunk_id=1,
        material_id=1,
        identificador_curto="P1",
        localizacao="página 1",
        texto="A busca em largura usa uma fila.",
        score=1.0,
        score_vetorial=1.0,
    )
]
_ORIENTACOES = [
    _NS(o_que_mudar="exemplos práticos", cruzar_com=None),
    _NS(o_que_mudar=None, cruzar_com="arquitetura de computadores"),
]
_MEDIA = _Faixa.MEDIA


def test_pedido_sem_orientacao_e_o_de_antes():
    """Regressão: toda geração sem orientação manda exatamente o pedido de antes."""
    esperado = "\n\n".join(
        [
            "Trechos disponíveis:\n" + _formatar_trechos(_TRECHOS),
            _contextualizacao(_MEDIA),
            (
                f"Gere UMA questão de dificuldade {_MEDIA.value}, usando apenas os "
                f"trechos acima. {_pedido_formato(_Formato.PROPOSICAO, None, 5)}"
            ),
        ]
    )
    assert _usuario_gerador(_TRECHOS, _MEDIA, 5, _Tipo.OBJETIVA) == esperado
    assert (
        _usuario_gerador(
            _TRECHOS, _MEDIA, 5, _Tipo.OBJETIVA, orientacoes=(), partida=False
        )
        == esperado
    )


def test_pedido_sem_orientacao_com_evitar_mantem_o_nao_repita():
    usuario = _usuario_gerador(
        _TRECHOS, _MEDIA, 5, _Tipo.OBJETIVA, evitar="Enunciado: X"
    )
    assert "Questão que está sendo substituída — não a repita." in usuario
    assert "Orientações do docente" not in usuario


def test_bloco_de_orientacoes_entre_trechos_e_contextualizacao():
    usuario = _usuario_gerador(
        _TRECHOS, _MEDIA, 5, _Tipo.OBJETIVA, orientacoes=_ORIENTACOES
    )
    bloco = (
        "Orientações do docente:\n1. Mudar: exemplos práticos\n"
        "2. Articular com: arquitetura de computadores"
    )
    assert bloco in usuario
    assert (
        usuario.index("Trechos disponíveis")
        < usuario.index(bloco)
        < usuario.index(_contextualizacao(_MEDIA))
    )


def test_variacao_guiada_troca_nao_repita_por_questao_de_partida():
    usuario = _usuario_gerador(
        _TRECHOS,
        _MEDIA,
        5,
        _Tipo.OBJETIVA,
        evitar="Enunciado: X",
        orientacoes=_ORIENTACOES[:1],
        partida=True,
    )
    assert (
        "Questão de partida: mantenha o que funciona nela e aplique a orientação.\n"
        "Enunciado: X"
    ) in usuario
    assert "não a repita" not in usuario
    assert (
        usuario.index("Orientações do docente")
        < usuario.index("Questão de partida")
        < usuario.index(_contextualizacao(_MEDIA))
    )
