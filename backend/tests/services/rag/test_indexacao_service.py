import json

import pytest

from backend.app.domain import EstadoSessao, OrigemTexto, TipoMaterial
from backend.app.exceptions import (
    ArtefatoDeTextoInvalidoException,
    FalhaEmbeddingException,
)
from backend.app.models.materiais import ChunkMaterial, MaterialReferencia
from backend.app.services.rag.chunking import ConfigChunking
from backend.app.services.rag.indexacao_service import indexar_sessao

CFG = ConfigChunking(max_chars=1200, overlap_chars=200, min_chars=300)


def artefato(blocos: list[tuple[str, str]]) -> bytes:
    return json.dumps(
        {
            "formato": "pdf",
            "blocos": [
                {"localizacao": loc, "texto": txt, "origem": OrigemTexto.NATIVO.value}
                for loc, txt in blocos
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")


def criar_material(db, armazenamento, sessao, identificador, blocos):
    chave = f"{sessao.docente_id}/{sessao.id}/{identificador}.extraido.json"
    armazenamento.salvar(chave, artefato(blocos))
    material = MaterialReferencia(
        sessao_id=sessao.id,
        identificador_curto=identificador,
        nome_arquivo=f"{identificador}.pdf",
        tipo=TipoMaterial.PDF,
        formato="pdf",
        status_legibilidade="legivel",
        contagem_paginas_logicas=len(blocos),
        chave_armazenamento=f"{sessao.docente_id}/{sessao.id}/{identificador}.pdf",
        chave_texto_extraido=chave,
        hash_sha256=identificador * 8,
        tamanho_bytes=100,
        origem_texto=OrigemTexto.NATIVO,
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return material


class EmbeddingsQueFalhaNoSegundo:
    """Duplo que falha a partir da segunda chamada: é assim que se prova a
    retomada sem depender de rede."""

    def __init__(self, bom, falhar_a_partir_de: int) -> None:
        self.bom = bom
        self.dimensao = bom.dimensao
        self.falhar_a_partir_de = falhar_a_partir_de
        self.chamadas = 0

    def embutir_documentos(self, textos):
        self.chamadas += 1
        if self.chamadas >= self.falhar_a_partir_de:
            raise FalhaEmbeddingException("connection refused")
        return self.bom.embutir_documentos(textos)

    def embutir_consulta(self, texto):
        return self.bom.embutir_consulta(texto)


def test_indexa_todos_os_materiais_pendentes(
    db_session, armazenamento, embeddings_fake, sessao_rascunho
):
    criar_material(
        db_session,
        armazenamento,
        sessao_rascunho,
        "P1",
        [("página 1", "conteúdo da primeira página " * 20)],
    )
    resumo = indexar_sessao(
        db_session, armazenamento, embeddings_fake, sessao_rascunho, CFG
    )
    assert resumo.materiais_indexados == 1
    assert resumo.chunks_criados >= 1
    material = db_session.query(MaterialReferencia).one()
    assert material.indexado_em is not None
    assert material.n_chunks == resumo.chunks_criados


def test_chunks_carregam_localizacao_e_ordem(
    db_session, armazenamento, embeddings_fake, sessao_rascunho
):
    criar_material(
        db_session,
        armazenamento,
        sessao_rascunho,
        "P1",
        [
            ("página 1", "primeira " * 60),
            ("página 2", "segunda " * 60),
        ],
    )
    indexar_sessao(db_session, armazenamento, embeddings_fake, sessao_rascunho, CFG)
    chunks = db_session.query(ChunkMaterial).order_by(ChunkMaterial.ordem).all()
    assert [c.ordem for c in chunks] == list(range(len(chunks)))
    assert all(c.localizacao for c in chunks)
    assert all(len(c.vetor_embedding) == embeddings_fake.dimensao for c in chunks)


def test_falha_no_segundo_material_preserva_o_primeiro(
    db_session, armazenamento, embeddings_fake, sessao_rascunho
):
    criar_material(
        db_session,
        armazenamento,
        sessao_rascunho,
        "P1",
        [("página 1", "primeiro material " * 30)],
    )
    criar_material(
        db_session,
        armazenamento,
        sessao_rascunho,
        "P2",
        [("página 1", "segundo material " * 30)],
    )
    ruim = EmbeddingsQueFalhaNoSegundo(embeddings_fake, falhar_a_partir_de=2)

    with pytest.raises(FalhaEmbeddingException):
        indexar_sessao(db_session, armazenamento, ruim, sessao_rascunho, CFG)

    materiais = (
        db_session.query(MaterialReferencia).order_by(MaterialReferencia.id).all()
    )
    assert materiais[0].indexado_em is not None
    assert materiais[1].indexado_em is None
    assert sessao_rascunho.estado == EstadoSessao.RASCUNHO


def test_retomada_so_processa_o_que_faltou(
    db_session, armazenamento, embeddings_fake, sessao_rascunho
):
    criar_material(
        db_session,
        armazenamento,
        sessao_rascunho,
        "P1",
        [("página 1", "primeiro material " * 30)],
    )
    criar_material(
        db_session,
        armazenamento,
        sessao_rascunho,
        "P2",
        [("página 1", "segundo material " * 30)],
    )
    ruim = EmbeddingsQueFalhaNoSegundo(embeddings_fake, falhar_a_partir_de=2)
    with pytest.raises(FalhaEmbeddingException):
        indexar_sessao(db_session, armazenamento, ruim, sessao_rascunho, CFG)

    resumo = indexar_sessao(
        db_session, armazenamento, embeddings_fake, sessao_rascunho, CFG
    )
    assert resumo.materiais_indexados == 1


def test_sessao_ja_confirmada_nao_reindexa(
    db_session, armazenamento, embeddings_fake, sessao_rascunho
):
    criar_material(
        db_session,
        armazenamento,
        sessao_rascunho,
        "P1",
        [("página 1", "conteúdo " * 40)],
    )
    sessao_rascunho.estado = EstadoSessao.MATERIAIS_CONFIRMADOS
    db_session.commit()
    resumo = indexar_sessao(
        db_session, armazenamento, embeddings_fake, sessao_rascunho, CFG
    )
    assert resumo.materiais_indexados == 0


def test_artefato_corrompido_falha_com_mensagem_util(
    db_session, armazenamento, embeddings_fake, sessao_rascunho
):
    material = criar_material(
        db_session,
        armazenamento,
        sessao_rascunho,
        "P1",
        [("página 1", "conteúdo " * 40)],
    )
    armazenamento.salvar(material.chave_texto_extraido, b"nao e json")
    with pytest.raises(ArtefatoDeTextoInvalidoException, match="P1"):
        indexar_sessao(db_session, armazenamento, embeddings_fake, sessao_rascunho, CFG)


def test_indexar_e_confirmar_pega_material_que_escorregou_no_meio(
    db_session, armazenamento, embeddings_fake, sessao_rascunho, monkeypatch
):
    """Race: upload concorrente comita um material entre a indexação e a
    promoção. indexar_e_confirmar re-trava, re-verifica e indexa o que chegou."""
    from sqlalchemy.orm import sessionmaker

    from backend.app.services.rag import indexacao_service
    from backend.app.services.rag.indexacao_service import indexar_e_confirmar

    criar_material(
        db_session,
        armazenamento,
        sessao_rascunho,
        "P1",
        [("página 1", "primeiro material " * 30)],
    )

    inserido = {"feito": False}
    real_indexar = indexacao_service.indexar_sessao

    def _indexar_e_inserir_concorrente(db, arm, emb, sessao, cfg):
        real_indexar(db, arm, emb, sessao, cfg)
        if not inserido["feito"]:
            inserido["feito"] = True
            outra = sessionmaker(bind=db.get_bind())()
            criar_material(
                outra, arm, sessao, "P2", [("página 1", "segundo material " * 30)]
            )
            outra.close()

    monkeypatch.setattr(
        indexacao_service, "indexar_sessao", _indexar_e_inserir_concorrente
    )

    sessao = indexar_e_confirmar(
        db_session, armazenamento, embeddings_fake, sessao_rascunho, CFG
    )
    assert sessao.estado == EstadoSessao.MATERIAIS_CONFIRMADOS
    materiais = (
        db_session.query(MaterialReferencia).order_by(MaterialReferencia.id).all()
    )
    assert [m.identificador_curto for m in materiais] == ["P1", "P2"]
    assert all(m.indexado_em is not None for m in materiais)


# --- Achado 13: o laço de confirmação tem cota de rodadas ---


def test_confirmar_com_uploads_sem_fim_levanta_em_vez_de_girar_para_sempre(monkeypatch):
    """Dublês no lugar da sessão e do banco: o que se testa é só o controle do
    laço. Um pendente que reaparece a cada rodada não pode prendê-lo."""
    from types import SimpleNamespace

    from backend.app.exceptions import SessaoEstadoInvalidaException
    from backend.app.services.rag import indexacao_service as modulo

    sessao = SimpleNamespace(id=1, estado=EstadoSessao.RASCUNHO)
    rodadas = []
    monkeypatch.setattr(modulo, "_travar_sessao", lambda db, sessao_id: sessao)
    monkeypatch.setattr(
        modulo, "indexar_sessao", lambda *args, **kwargs: rodadas.append(1)
    )

    class DbSempreComPendente:
        def scalar(self, _consulta):
            return 99  # sempre há um material pendente

    with pytest.raises(SessaoEstadoInvalidaException):
        modulo.indexar_e_confirmar(DbSempreComPendente(), None, None, sessao, CFG)

    assert len(rodadas) == modulo.MAX_RODADAS_CONFIRMACAO
