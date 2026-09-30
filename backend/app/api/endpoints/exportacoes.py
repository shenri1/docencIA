"""Download de arquivo exportado. Devolve o que SAIU, não o estado atual."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_docente
from backend.app.core.db import get_db
from backend.app.core.storage import ArmazenamentoArquivos, get_armazenamento
from backend.app.models.identidade import Docente
from backend.app.services.exportacao.exportacao_service import abrir_exportacao

router = APIRouter(prefix="/exportacoes/{exportacao_id}", tags=["Exportação"])

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("/arquivo")
def baixar(
    exportacao_id: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
    armazenamento: ArmazenamentoArquivos = Depends(get_armazenamento),
) -> Response:
    exportacao, dados = abrir_exportacao(db, docente, armazenamento, exportacao_id)
    # banco_id, não banco.versao: a versão vem da entrada do docente, só com
    # max_length, e aspas ou quebra de linha nela quebrariam o cabeçalho.
    nome = (
        f"prova-banco{exportacao.banco_id}-r{exportacao.revisao_banco}-"
        f"{exportacao.tipo.value}.docx"
    )
    return Response(
        content=dados,
        media_type=_DOCX,
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
