"""Importa todos os modelos para popular `Base.metadata` (create_all/Alembic)."""

from backend.app.models.auditoria import RegistroAuditoria
from backend.app.models.banco import (
    Alternativa,
    AspectoEsperado,
    BancoQuestoes,
    FonteInterna,
    JustificativaEstruturada,
    Questao,
    RegistroExclusao,
    RegistroSubstituicao,
    RelatorioImpacto,
    RevisaoQuestao,
)
from backend.app.models.base import Base
from backend.app.models.identidade import Docente, SessaoGeracao
from backend.app.models.materiais import ChunkMaterial, MaterialReferencia
from backend.app.models.metricas import MetricaGeracao
from backend.app.models.orientacoes import OrientacaoDocente, questoes_orientacoes
from backend.app.models.prompt_provedor import ConsumoToken, PromptMestre, ProvedorLLM
from backend.app.models.provas import ExportacaoDocx, Gabarito, ItemProva, Prova

__all__ = [
    "Alternativa",
    "AspectoEsperado",
    "BancoQuestoes",
    "Base",
    "ChunkMaterial",
    "ConsumoToken",
    "Docente",
    "ExportacaoDocx",
    "FonteInterna",
    "Gabarito",
    "ItemProva",
    "JustificativaEstruturada",
    "MaterialReferencia",
    "MetricaGeracao",
    "OrientacaoDocente",
    "PromptMestre",
    "Prova",
    "ProvedorLLM",
    "Questao",
    "RegistroAuditoria",
    "RegistroExclusao",
    "RegistroSubstituicao",
    "RelatorioImpacto",
    "RevisaoQuestao",
    "SessaoGeracao",
    "questoes_orientacoes",
]
