"""Grava a linha de `metricas_geracao` de uma tentativa.

Roda depois do commit da questão: a transação dela não fica aberta durante o
juiz em CPU, e uma falha aqui não a alcança. A linha é inserida uma vez só, já
completa. Núcleo Semântico, porque a aderência chama o juiz.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from backend.app.domain import (
    EstadoQuestao,
    FaixaDificuldade,
    FormatoItem,
    TipoQuestao,
)
from backend.app.models.banco import BancoQuestoes
from backend.app.models.identidade import SessaoGeracao
from backend.app.models.metricas import MetricaGeracao
from backend.app.services.metricas.aderencia import medir_aderencia
from backend.app.services.metricas.coletor import Coletor
from backend.app.services.metricas.juiz import Juiz
from backend.app.services.metricas.sustentacao import medir_sustentacao
from backend.app.services.rag.embeddings import Embeddings

if TYPE_CHECKING:
    from backend.app.services.geracao.banco_service import Improdutiva, Produzida

_log = logging.getLogger(__name__)


def registrar_tentativa(
    db: Session,
    *,
    coletor: Coletor,
    banco: BancoQuestoes,
    sessao: SessaoGeracao,
    numero: int,
    tipo: TipoQuestao,
    faixa: FaixaDificuldade,
    formato_planejado: FormatoItem,
    estado: EstadoQuestao,
    produzida: Produzida | Improdutiva,
    embeddings: Embeddings,
    juiz: Juiz | None,
) -> None:
    """Nunca levanta: a métrica observa, e a questão já está salva."""
    banco_id = banco.id  # antes do try: no except o objeto pode estar expirado
    try:
        questao = getattr(produzida, "questao", None)
        sustentacao = aderencia = None
        if questao is not None:
            sustentacao = medir_sustentacao(questao, coletor.trechos_enviados)
            aderencia = medir_aderencia(
                questao,
                sessao,
                [f.trecho_base for f in questao.fontes_internas],
                embeddings,
                juiz,
                coletor,
            )
        coletor.fechar()
        final = coletor.formato_final
        db.add(
            MetricaGeracao(
                banco_id=banco_id,
                numero=numero,
                questao_id=questao.id if questao is not None else None,
                origem=(
                    "substituicao" if estado is EstadoQuestao.CANDIDATA else "geracao"
                ),
                desfecho="produzida" if questao is not None else produzida.desfecho,
                motivo=None if questao is not None else produzida.motivo,
                tipo=tipo.value,
                faixa=faixa.value,
                formato_planejado=formato_planejado.value,
                formato_final=final.value if final is not None else None,
                motivo_recuo=coletor.motivo_recuo,
                modelo_geracao=coletor.modelo_geracao,
                modelo_revisao=coletor.modelo_revisao,
                iniciada_em=coletor.iniciada_em,
                tempos_ms=coletor.tempos_ms,
                tokens=coletor.tokens,
                rag=coletor.rag,
                sustentacao=sustentacao,
                aderencia=aderencia,
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001  # observador: a questão já está commitada
        db.rollback()
        _log.exception("métrica do número %s do banco %s não gravada", numero, banco_id)
