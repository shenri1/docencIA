"""Exportação DOCX — orquestração de caso de uso.

Confere, renderiza, grava. O arquivo SAI do sistema, e por isso é gravado junto
de um registro append-only: depois que a revisão do banco muda, só o registro
prova o que foi entregue.
"""

from __future__ import annotations

import dataclasses
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.storage import ArmazenamentoArquivos
from backend.app.domain import (
    EstadoSessao,
    TipoEventoAuditoria,
    TipoExportacao,
    TipoGabarito,
)
from backend.app.exceptions import (
    ArquivoExportadoCorrompidoException,
    ExportacaoNaoEncontradaException,
)
from backend.app.models.banco import BancoQuestoes
from backend.app.models.identidade import Docente
from backend.app.models.provas import ExportacaoDocx
from backend.app.services.controle_banco.estado import obter_banco
from backend.app.services.critico.auditor_service import montar_resumo
from backend.app.services.exportacao.consistencia import verificar_exportavel
from backend.app.services.exportacao.renderizacao import (
    Cabecalho,
    renderizar_conteudo_puro,
    renderizar_metadados,
)
from backend.app.services.log_auditoria import registrar_evento
from backend.app.services.provas.gabarito import gerar_gabarito
from backend.app.services.provas.leitura import ler_prova
from backend.app.services.provas.verificacao import verificar_provas


def _chave(banco: BancoQuestoes, tipo: TipoExportacao) -> str:
    """Determinística: se o commit falhar depois do salvamento, a próxima
    tentativa sobrescreve com os mesmos bytes, sem limpeza."""
    sessao = banco.sessao
    return (
        f"{sessao.docente_id}/{sessao.id}/exportacoes/"
        f"{banco.id}-r{banco.revisao}-{tipo.value}.docx"
    )


def _da_revisao(db: Session, banco: BancoQuestoes) -> list[ExportacaoDocx]:
    return list(
        db.scalars(
            select(ExportacaoDocx)
            .where(
                ExportacaoDocx.banco_id == banco.id,
                ExportacaoDocx.revisao_banco == banco.revisao,
            )
            .order_by(ExportacaoDocx.tipo)
        )
    )


def exportar(
    db: Session,
    docente: Docente,
    armazenamento: ArmazenamentoArquivos,
    banco: BancoQuestoes,
) -> list[ExportacaoDocx]:
    # Sempre primeiro, inclusive quando a exportação já existe: pular a checagem
    # num atalho faria "estado incoerente responde 409" depender de ter
    # exportado antes.
    prova_a, prova_b = verificar_exportavel(db, docente, banco)

    existentes = _da_revisao(db, banco)
    if existentes:
        # Um commit grava os dois: ou existem os dois, ou nenhum.
        return existentes

    sessao = banco.sessao
    cabecalho = Cabecalho(
        disciplina=sessao.disciplina,
        periodo=sessao.periodo,
        versao_banco=banco.versao,
        revisao_banco=banco.revisao,
    )
    lida_a = ler_prova(db, docente, prova_a.id)
    lida_b = ler_prova(db, docente, prova_b.id)
    # Achados de auditoria só das questões que estão nas provas.
    numeros = {item.numero for prova in (lida_a, lida_b) for item in prova.itens}
    auditoria = montar_resumo(db, banco)
    auditoria = dataclasses.replace(
        auditoria, questoes=[q for q in auditoria.questoes if q.numero in numeros]
    )

    arquivos = {
        TipoExportacao.CONTEUDO_PURO: renderizar_conteudo_puro(
            cabecalho, lida_a, lida_b
        ),
        TipoExportacao.METADADOS: renderizar_metadados(
            cabecalho,
            gerar_gabarito(db, docente, prova_a.id, TipoGabarito.COMENTADO),
            gerar_gabarito(db, docente, prova_b.id, TipoGabarito.COMENTADO),
            verificar_provas(db, prova_a, prova_b),
            auditoria,
        ),
    }

    registros: list[ExportacaoDocx] = []
    for tipo, dados in arquivos.items():
        chave = _chave(banco, tipo)
        armazenamento.salvar(chave, dados)
        registro = ExportacaoDocx(
            banco_id=banco.id,
            revisao_banco=banco.revisao,
            tipo=tipo,
            caminho_arquivo=chave,
            hash_conteudo=hashlib.sha256(dados).hexdigest(),
        )
        db.add(registro)
        registros.append(registro)
    sessao.estado = EstadoSessao.EXPORTADO
    db.flush()  # ids dos registros, para o evento
    registrar_evento(
        db,
        TipoEventoAuditoria.EXPORTACAO_DOCX,
        f"bancos_questoes:{banco.id}",
        docente.id,
        {
            "revisao_banco": banco.revisao,
            "exportacoes": [
                {"id": r.id, "tipo": r.tipo.value, "hash_conteudo": r.hash_conteudo}
                for r in registros
            ],
        },
    )
    db.commit()
    return registros


def listar_exportacoes(
    db: Session, docente: Docente, banco_id: int
) -> list[ExportacaoDocx]:
    banco = obter_banco(db, docente, banco_id)
    return list(
        db.scalars(
            select(ExportacaoDocx)
            .where(ExportacaoDocx.banco_id == banco.id)
            .order_by(ExportacaoDocx.revisao_banco, ExportacaoDocx.tipo)
        )
    )


def abrir_exportacao(
    db: Session,
    docente: Docente,
    armazenamento: ArmazenamentoArquivos,
    exportacao_id: int,
) -> tuple[ExportacaoDocx, bytes]:
    """Devolve o que SAIU, não o estado atual: não passa por verificar_exportavel,
    e continua funcionando depois que a revisão do banco muda."""
    exportacao = db.get(ExportacaoDocx, exportacao_id)
    if (
        exportacao is None
        or exportacao.banco is None
        or exportacao.banco.sessao.docente_id != docente.id
    ):
        raise ExportacaoNaoEncontradaException(exportacao_id)
    dados = armazenamento.abrir(exportacao.caminho_arquivo)
    if hashlib.sha256(dados).hexdigest() != exportacao.hash_conteudo:
        raise ArquivoExportadoCorrompidoException(exportacao_id)
    return exportacao, dados
