"""Agente Orquestrador — Orquestração de UC.

Decide sem LLM: o marco sai do estado gravado (`marco.py`), e o comando é
despachado para o service do passo, que continua validando o que valida.
Gerar e auditar chamam LLM dentro dos services deles; aqui o provedor só é
repassado, e por isso nada deste pacote importa de `services/provedor/` nem de
`prompt/`.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.domain import (
    ComandoOrquestrador,
    EstadoSessao,
    Marco,
    TipoGabarito,
)
from backend.app.exceptions import (
    CamposDoMarcoException,
    ComandoForaDoMarcoException,
)
from backend.app.models.banco import BancoQuestoes, RelatorioImpacto
from backend.app.models.identidade import Docente, SessaoGeracao
from backend.app.models.materiais import MaterialReferencia
from backend.app.models.provas import ExportacaoDocx
from backend.app.schemas.orquestrador import (
    ComandoAuditar,
    ComandoExcluir,
    ComandoProsseguir,
)
from backend.app.services.controle_banco.catalogo import ItemCatalogo, catalogar
from backend.app.services.controle_banco.estado import exigir_revisao
from backend.app.services.controle_banco.exclusao_service import (
    congelar_banco,
    excluir_questoes,
)
from backend.app.services.critico.auditor_service import (
    ResumoAuditoria,
    auditar_banco,
)
from backend.app.services.exportacao.exportacao_service import exportar
from backend.app.services.geracao.banco_service import ResumoBanco, gerar_banco
from backend.app.services.material_service import listar_indice
from backend.app.services.orquestrador.marco import (
    CAMPOS_PROSSEGUIR,
    COMANDOS,
    MarcoSessao,
    banco_da_versao,
    classificar_banco,
    marco_da_sessao,
)
from backend.app.services.provas.gabarito import Gabarito, gerar_gabarito
from backend.app.services.provas.montagem_service import (
    ProvasMontadas,
    montar_provas,
)
from backend.app.services.rag.chunking import ConfigChunking
from backend.app.services.rag.indexacao_service import indexar_e_confirmar

_CAMPOS = ("versao", "revisao_esperada", "n_objetivas", "n_discursivas")


@dataclass(frozen=True)
class Indice:
    """Mesma forma de `IndiceResposta`, lida por `listar_indice`."""

    materiais: list[MaterialReferencia]
    confirmado: bool


@dataclass(frozen=True)
class ResultadoComando:
    """Um campo de resultado por passo; os demais ficam None. O cliente sabe
    qual ler por `comando` e `marco_executado`."""

    comando: ComandoOrquestrador
    marco_executado: Marco
    marco: MarcoSessao
    indice: Indice | None = None
    banco: ResumoBanco | None = None
    relatorio: RelatorioImpacto | None = None
    catalogo: list[ItemCatalogo] | None = None
    provas: ProvasMontadas | None = None
    gabaritos: list[Gabarito] | None = None
    exportacoes: list[ExportacaoDocx] | None = None
    auditoria: ResumoAuditoria | None = None


def _alvo(
    db: Session, sessao: SessaoGeracao, versao: str | None
) -> tuple[Marco, str | None, BancoQuestoes | None]:
    """Marco, motivo (só em BLOQUEADO) e banco do comando."""
    if sessao.estado is EstadoSessao.RASCUNHO:
        # Em M1 o alvo é sempre a sessão; uma `versao` no prosseguir é sobra.
        return Marco.M1_MATERIAIS, None, None
    banco = banco_da_versao(db, sessao, versao) if versao is not None else None
    if banco is None:
        # Versão inexistente é o M2 dela, que só aceita prosseguir: excluir e
        # auditar caem em COMANDO_FORA_DO_MARCO sem caso especial.
        return Marco.M2_BANCO, None, None
    marco, motivo = classificar_banco(db, banco)
    return marco, motivo, banco


def _conferir_campos(comando: ComandoProsseguir, marco: Marco) -> None:
    esperados = CAMPOS_PROSSEGUIR[marco]
    presentes = {c for c in _CAMPOS if getattr(comando, c) is not None}
    faltando = [c for c in esperados if c not in presentes]
    sobrando = [c for c in _CAMPOS if c in presentes and c not in esperados]
    if faltando or sobrando:
        raise CamposDoMarcoException(marco.value, list(esperados), faltando, sobrando)


def executar_comando(
    db: Session,
    docente: Docente,
    sessao: SessaoGeracao,
    comando: ComandoProsseguir | ComandoExcluir | ComandoAuditar,
    *,
    armazenamento,
    embeddings,
    reranker,
    provedor,
) -> ResultadoComando:
    tipo = ComandoOrquestrador(comando.comando)
    marco, motivo, banco = _alvo(db, sessao, comando.versao)
    if tipo not in COMANDOS[marco]:
        raise ComandoForaDoMarcoException(
            marco.value, [c.value for c in COMANDOS[marco]], motivo
        )
    if isinstance(comando, ComandoProsseguir):
        _conferir_campos(comando, marco)
    revisao = getattr(comando, "revisao_esperada", None)
    if banco is not None and revisao is not None:
        # Vale também no M10, cuja rota de origem não pede revisão.
        exigir_revisao(banco, revisao)

    resultado: dict = {}
    if isinstance(comando, ComandoExcluir):
        resultado["relatorio"] = excluir_questoes(
            db, docente, banco, comando.numeros, comando.revisao_esperada
        )
    elif isinstance(comando, ComandoAuditar):
        resultado["auditoria"] = auditar_banco(
            db, embeddings, reranker, provedor, docente, banco
        )
    elif marco is Marco.M1_MATERIAIS:
        sessao = indexar_e_confirmar(
            db, armazenamento, embeddings, sessao, ConfigChunking.das_settings()
        )
        resultado["indice"] = Indice(*listar_indice(db, sessao))
    elif marco is Marco.M2_BANCO:
        resultado["banco"] = gerar_banco(
            db,
            embeddings,
            reranker,
            provedor,
            sessao,
            n_objetivas=comando.n_objetivas,
            n_discursivas=comando.n_discursivas,
            versao=comando.versao,
        )
    elif marco is Marco.M3_EXCLUSOES:
        resultado["relatorio"] = congelar_banco(
            db, docente, banco, comando.revisao_esperada
        )
        # M5 embutido: o catálogo não tem decisão.
        resultado["catalogo"] = catalogar(db, banco)
    elif marco is Marco.M6_PROVAS:
        provas = montar_provas(
            db,
            docente,
            banco,
            comando.n_objetivas,
            comando.n_discursivas,
            comando.revisao_esperada,
        )
        # M7 (verificação) já vem em `provas`; M8 embutido. M9 é "se
        # solicitado" e fica na rota de gabarito.
        resultado["provas"] = provas
        resultado["gabaritos"] = [
            gerar_gabarito(db, docente, prova_id, TipoGabarito.SIMPLES)
            for prova_id in (provas.prova_a_id, provas.prova_b_id)
        ]
    else:  # M10_DOCX: COMANDOS já barrou CONCLUIDO e BLOQUEADO.
        resultado["exportacoes"] = exportar(db, docente, armazenamento, banco)

    return ResultadoComando(
        comando=tipo,
        marco_executado=marco,
        marco=marco_da_sessao(db, sessao),
        **resultado,
    )
