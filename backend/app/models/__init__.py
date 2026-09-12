"""Importa todos os modelos para popular `Base.metadata` (create_all/Alembic)."""

from backend.app.models.auditoria import RegistroAuditoria
from backend.app.models.banco import (
    Alternativa,
    BancoQuestoes,
    FonteInterna,
    JustificativaEstruturada,
    Questao,
    RegistroExclusao,
    RelatorioImpacto,
)
from backend.app.models.base import Base
from backend.app.models.identidade import Docente, SessaoGeracao
from backend.app.models.materiais import ChunkMaterial, MaterialReferencia
from backend.app.models.prompt_provedor import ConsumoToken, PromptMestre, ProvedorLLM
from backend.app.models.provas import ExportacaoDocx, Gabarito, ItemProva, Prova

__all__ = [
    "Alternativa",
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
    "PromptMestre",
    "Prova",
    "ProvedorLLM",
    "Questao",
    "RegistroAuditoria",
    "RegistroExclusao",
    "RelatorioImpacto",
    "SessaoGeracao",
]
