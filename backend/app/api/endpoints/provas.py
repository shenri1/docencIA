"""Leitura de prova. A montagem fica em `endpoints/bancos.py`, porque é ato
sobre o banco — mesmo critério que separa `banco.py` de `bancos.py`."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_docente
from backend.app.core.db import get_db
from backend.app.domain import TipoGabarito
from backend.app.models.identidade import Docente
from backend.app.schemas.prova import (
    GabaritoResposta,
    ProvaResposta,
    VerificacaoResposta,
)
from backend.app.services.provas.gabarito import Gabarito, gerar_gabarito
from backend.app.services.provas.leitura import (
    ProvaLida,
    ler_prova,
    obter_prova,
    par_da_prova,
)
from backend.app.services.provas.verificacao import Verificacao, verificar_provas

router = APIRouter(prefix="/provas/{prova_id}", tags=["Provas"])


@router.get("", response_model=ProvaResposta)
def ler(
    prova_id: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> ProvaLida:
    return ler_prova(db, docente, prova_id)


@router.get("/verificacao", response_model=VerificacaoResposta)
def verificacao(
    prova_id: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> Verificacao:
    """Recomputada a cada chamada: é função pura sobre as ItemProva, e coluna
    derivada seria mais um lugar para divergir."""
    prova = obter_prova(db, docente, prova_id)
    a, b = sorted((prova, par_da_prova(db, prova)), key=lambda p: p.versao)
    return verificar_provas(db, a, b)


@router.get("/gabarito", response_model=GabaritoResposta)
def gabarito(
    prova_id: int,
    # Obrigatória, sem default: o comentado expõe a justificativa estruturada, e
    # isso não deve acontecer por omissão de parâmetro. A chamada é o pedido
    # explícito.
    modalidade: TipoGabarito = Query(...),
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> Gabarito:
    return gerar_gabarito(db, docente, prova_id, modalidade)
