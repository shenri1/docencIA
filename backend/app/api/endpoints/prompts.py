from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.api.deps import require_perfil
from backend.app.core.db import get_db
from backend.app.domain import PerfilDocente
from backend.app.models.prompt_provedor import PromptMestre
from backend.app.prompt.parametros import ParametrosGeracao
from backend.app.schemas.prompt import PromptCriar, PromptResposta
from backend.app.services.prompt_mestre_service import (
    ativar,
    listar_versoes,
    obter_ativo,
    registrar_versao,
)

# Primeira rota do projeto a exigir perfil acima de `docente`: mexer no prompt
# mestre muda o comportamento do sistema inteiro. A dependência entra no
# router, não rota a rota — assim nenhuma rota nova nasce desprotegida por
# esquecimento.
router = APIRouter(
    prefix="/prompts",
    tags=["Prompt Mestre"],
    dependencies=[Depends(require_perfil(PerfilDocente.ADMINISTRADOR))],
)


@router.get("", response_model=list[PromptResposta])
def listar(db: Session = Depends(get_db)) -> list[PromptMestre]:
    return listar_versoes(db)


@router.get("/ativo", response_model=PromptResposta)
def ativo(db: Session = Depends(get_db)) -> PromptMestre:
    return obter_ativo(db)


@router.post("", response_model=PromptResposta, status_code=status.HTTP_201_CREATED)
def criar(dados: PromptCriar, db: Session = Depends(get_db)) -> PromptMestre:
    params = ParametrosGeracao(
        disciplina=dados.disciplina,
        periodo=dados.periodo,
        area_do_conhecimento=dados.area_do_conhecimento,
        tema_escopo=dados.tema_escopo,
        k_alternativas=dados.k_alternativas,
        n_faceis=dados.n_faceis,
        n_medias=dados.n_medias,
        n_dificeis=dados.n_dificeis,
    )
    return registrar_versao(db, dados.versao, dados.papel_definido, params)


@router.post("/{versao}/ativar", response_model=PromptResposta)
def ativar_versao(versao: str, db: Session = Depends(get_db)) -> PromptMestre:
    return ativar(db, versao)
