from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_docente
from backend.app.core.config import settings
from backend.app.core.db import get_db
from backend.app.core.storage import ArmazenamentoArquivos, get_armazenamento
from backend.app.domain import TipoMaterial
from backend.app.models.identidade import Docente
from backend.app.models.materiais import MaterialReferencia
from backend.app.schemas.material import IndiceResposta, MaterialResposta
from backend.app.services.extracao import (
    ConfigExtracao,
    Ocr,
    OcrTesseract,
    ocr_disponivel,
)
from backend.app.services.material_service import (
    ler_com_limite,
    listar_indice,
    registrar_material,
    remover_material,
)
from backend.app.services.rag.chunking import ConfigChunking
from backend.app.services.rag.embeddings import Embeddings, get_embeddings
from backend.app.services.rag.indexacao_service import indexar_e_confirmar
from backend.app.services.sessao_service import obter_sessao

router = APIRouter(prefix="/sessoes/{sessao_id}/materiais", tags=["Materiais"])


def get_ocr() -> Ocr | None:
    if not settings.ocr_enabled or not ocr_disponivel():
        return None
    return OcrTesseract()


def _montar_indice(db: Session, sessao) -> IndiceResposta:
    materiais, confirmado = listar_indice(db, sessao)
    return IndiceResposta(
        materiais=[MaterialResposta.model_validate(m) for m in materiais],
        confirmado=confirmado,
    )


@router.post("", response_model=MaterialResposta, status_code=status.HTTP_201_CREATED)
def enviar(
    sessao_id: int,
    tipo: Annotated[
        TipoMaterial, Form(description="Classificação didática do material.")
    ],
    arquivo: Annotated[UploadFile, File(description="PDF, PPTX, DOCX ou TXT.")],
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
    armazenamento: ArmazenamentoArquivos = Depends(get_armazenamento),
    ocr: Ocr | None = Depends(get_ocr),
) -> MaterialReferencia:
    sessao = obter_sessao(db, docente, sessao_id)
    dados = ler_com_limite(arquivo.file, settings.max_upload_mb * 1024 * 1024)
    return registrar_material(
        db,
        armazenamento,
        docente,
        sessao,
        tipo,
        arquivo.filename or "sem-nome",
        dados,
        ConfigExtracao.das_settings(),
        ocr,
    )


@router.get("/indice", response_model=IndiceResposta)
def indice(
    sessao_id: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> IndiceResposta:
    return _montar_indice(db, obter_sessao(db, docente, sessao_id))


@router.post("/confirmar", response_model=IndiceResposta)
def confirmar(
    sessao_id: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
    armazenamento: ArmazenamentoArquivos = Depends(get_armazenamento),
    embeddings: Embeddings = Depends(get_embeddings),
) -> IndiceResposta:
    sessao = obter_sessao(db, docente, sessao_id)
    # A sessão só é promovida depois de TUDO indexado: sessão confirmada
    # implica sessão inteiramente indexada.
    sessao = indexar_e_confirmar(
        db, armazenamento, embeddings, sessao, ConfigChunking.das_settings()
    )
    return _montar_indice(db, sessao)


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(
    sessao_id: int,
    material_id: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
    armazenamento: ArmazenamentoArquivos = Depends(get_armazenamento),
) -> Response:
    sessao = obter_sessao(db, docente, sessao_id)
    remover_material(db, armazenamento, sessao, material_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
