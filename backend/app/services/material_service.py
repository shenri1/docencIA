"""Casos de uso de materiais — Núcleo Determinístico, nunca chama LLM.

O upload é síncrono e atômico: se qualquer etapa falha, nenhum arquivo e
nenhuma linha permanecem."""

import hashlib
import json
import uuid
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.storage import ArmazenamentoArquivos, montar_chave
from backend.app.domain import (
    EstadoSessao,
    StatusLegibilidade,
    TipoMaterial,
)
from backend.app.exceptions import (
    ArquivoMuitoGrandeException,
    IndiceVazioException,
    MaterialDuplicadoException,
    MaterialNaoEncontradoException,
    SessaoEstadoInvalidaException,
)
from backend.app.models.identidade import Docente, SessaoGeracao
from backend.app.models.materiais import MaterialReferencia
from backend.app.services.extracao import (
    ConfigExtracao,
    Ocr,
    detectar_formato,
    extrair_material,
)

_PREFIXO_POR_TIPO = {
    TipoMaterial.SLIDE: "S",
    TipoMaterial.PDF: "P",
    TipoMaterial.LIVRO: "L",
}
_TAMANHO_PEDACO = 1024 * 1024


def ler_com_limite(arquivo: BinaryIO, max_bytes: int) -> bytes:
    """Lê em pedaços e aborta assim que passa do limite — não carrega um
    arquivo gigante inteiro só para então rejeitá-lo."""
    pedacos: list[bytes] = []
    total = 0
    while pedaco := arquivo.read(_TAMANHO_PEDACO):
        total += len(pedaco)
        if total > max_bytes:
            raise ArquivoMuitoGrandeException(max_bytes // (1024 * 1024))
        pedacos.append(pedaco)
    return b"".join(pedacos)


def _travar_sessao(db: Session, sessao_id: int) -> SessaoGeracao:
    """Trava a linha da sessão (FOR UPDATE) e devolve o estado fresco.

    O lock vem antes de QUALQUER leitura (estado, hash, identificador): sem
    isso, um upload concorrente com POST /confirmar leria o estado como
    "rascunho" e gravaria material numa sessão já congelada.
    populate_existing re-lê o estado sob o lock — o objeto pode já estar no
    identity map com `estado` obsoleto (lido antes do freeze)."""
    return db.get(
        SessaoGeracao, sessao_id, with_for_update=True, populate_existing=True
    )


def _exigir_rascunho(sessao: SessaoGeracao) -> None:
    if sessao.estado != EstadoSessao.RASCUNHO:
        raise SessaoEstadoInvalidaException(
            "o índice de materiais já foi confirmado e está congelado"
        )


def _proximo_identificador(db: Session, sessao: SessaoGeracao, prefixo: str) -> str:
    # A linha da sessão já está travada pelo chamador (registrar_material), o
    # que serializa dois uploads simultâneos no cálculo da sequência.
    existentes = db.scalars(
        select(MaterialReferencia.identificador_curto).where(
            MaterialReferencia.sessao_id == sessao.id
        )
    )
    numeros = [
        int(valor[1:])
        for valor in existentes
        if valor.startswith(prefixo) and valor[1:].isdigit()
    ]
    return f"{prefixo}{max(numeros, default=0) + 1}"


def registrar_material(
    db: Session,
    armazenamento: ArmazenamentoArquivos,
    docente: Docente,
    sessao: SessaoGeracao,
    tipo: TipoMaterial,
    nome_arquivo: str,
    dados: bytes,
    cfg: ConfigExtracao,
    ocr: Ocr | None,
) -> MaterialReferencia:
    sessao = _travar_sessao(db, sessao.id)
    _exigir_rascunho(sessao)
    formato = detectar_formato(nome_arquivo, dados)

    hash_sha256 = hashlib.sha256(dados).hexdigest()
    ja_existe = db.scalar(
        select(MaterialReferencia).where(
            MaterialReferencia.sessao_id == sessao.id,
            MaterialReferencia.hash_sha256 == hash_sha256,
        )
    )
    if ja_existe is not None:
        raise MaterialDuplicadoException(ja_existe.identificador_curto)

    resultado = extrair_material(formato, dados, cfg, ocr)

    # O nome enviado pelo cliente é só metadado: o caminho é sempre UUID.
    identificador_arquivo = uuid.uuid4().hex
    chave_arquivo = montar_chave(
        docente.id, sessao.id, f"{identificador_arquivo}.{formato.value}"
    )
    chave_texto = montar_chave(
        docente.id, sessao.id, f"{identificador_arquivo}.extraido.json"
    )
    artefato = json.dumps(
        {
            "formato": formato.value,
            "blocos": [
                {
                    "localizacao": bloco.localizacao,
                    "texto": bloco.texto,
                    "origem": bloco.origem.value,
                }
                for bloco in resultado.blocos
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")

    try:
        # Os dois salvar ficam dentro do try: se o segundo falhar, o primeiro
        # (já gravado) é removido no except, sem deixar arquivo órfão no
        # storage. remover é idempotente, então o cleanup cobre também o caso
        # do primeiro salvar falhar antes de gravar qualquer coisa.
        armazenamento.salvar(chave_arquivo, dados)
        armazenamento.salvar(chave_texto, artefato)

        material = MaterialReferencia(
            sessao_id=sessao.id,
            identificador_curto=_proximo_identificador(
                db, sessao, _PREFIXO_POR_TIPO[tipo]
            ),
            nome_arquivo=Path(nome_arquivo).name[:255],
            tipo=tipo,
            formato=formato,
            status_legibilidade=StatusLegibilidade.LEGIVEL,
            contagem_paginas_logicas=resultado.contagem_paginas_logicas,
            chave_armazenamento=chave_arquivo,
            chave_texto_extraido=chave_texto,
            hash_sha256=hash_sha256,
            tamanho_bytes=len(dados),
            origem_texto=resultado.origem_texto,
        )
        db.add(material)
        db.commit()
        db.refresh(material)
        return material
    except IntegrityError:
        # Dois uploads simultâneos do mesmo arquivo passam ambos na checagem
        # de hash acima (ela é um SELECT sem lock) e o segundo estoura a
        # UniqueConstraint material_por_sessao_hash no commit — traduz para a
        # mesma resposta de duplicata do caminho "feliz", nunca 500.
        db.rollback()
        armazenamento.remover(chave_arquivo)
        armazenamento.remover(chave_texto)
        existente = db.scalar(
            select(MaterialReferencia).where(
                MaterialReferencia.sessao_id == sessao.id,
                MaterialReferencia.hash_sha256 == hash_sha256,
            )
        )
        identificador = existente.identificador_curto if existente else "?"
        raise MaterialDuplicadoException(identificador) from None
    except BaseException:
        db.rollback()
        armazenamento.remover(chave_arquivo)
        armazenamento.remover(chave_texto)
        raise


def listar_indice(
    db: Session, sessao: SessaoGeracao
) -> tuple[list[MaterialReferencia], bool]:
    materiais = list(
        db.scalars(
            select(MaterialReferencia)
            .where(MaterialReferencia.sessao_id == sessao.id)
            .order_by(MaterialReferencia.id)
        )
    )
    return materiais, sessao.estado != EstadoSessao.RASCUNHO


def remover_material(
    db: Session,
    armazenamento: ArmazenamentoArquivos,
    sessao: SessaoGeracao,
    material_id: int,
) -> None:
    sessao = _travar_sessao(db, sessao.id)
    _exigir_rascunho(sessao)
    material = db.scalar(
        select(MaterialReferencia).where(
            MaterialReferencia.id == material_id,
            MaterialReferencia.sessao_id == sessao.id,
        )
    )
    if material is None:
        raise MaterialNaoEncontradoException(material_id)
    chaves = (material.chave_armazenamento, material.chave_texto_extraido)
    db.delete(material)
    db.commit()
    for chave in chaves:
        armazenamento.remover(chave)


def confirmar_indice(db: Session, sessao: SessaoGeracao) -> SessaoGeracao:
    """a partir daqui o índice está congelado. Confirmar de novo é
    idempotente."""
    if sessao.estado != EstadoSessao.RASCUNHO:
        return sessao
    materiais, _ = listar_indice(db, sessao)
    if not materiais:
        raise IndiceVazioException()
    sessao.estado = EstadoSessao.MATERIAIS_CONFIRMADOS
    db.commit()
    db.refresh(sessao)
    return sessao
