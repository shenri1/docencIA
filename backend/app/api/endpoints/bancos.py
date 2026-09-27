"""Controle do banco.

Atenção: `endpoints/banco.py` é outro arquivo, com prefixo `/sessoes/{sessao_id}`
e a rota de geração. Conferir o prefixo antes de acrescentar rota aqui.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_docente, get_provedor
from backend.app.core.db import get_db
from backend.app.models.banco import RelatorioImpacto
from backend.app.models.identidade import Docente
from backend.app.schemas.banco import (
    BancoResposta,
    ComandoRevisao,
    ExclusaoCriar,
    PropostaSubstituicaoResposta,
    QuestaoResposta,
    RejeicaoResposta,
    RelatorioImpactoResposta,
    ResumoAuditoriaResposta,
)
from backend.app.services.controle_banco.estado import obter_banco
from backend.app.services.controle_banco.exclusao_service import (
    congelar_banco,
    excluir_questoes,
)
from backend.app.services.controle_banco.leitura import (
    BancoLido,
    ler_banco,
    listar_relatorios,
    questao_lida,
)
from backend.app.services.controle_banco.substituicao_service import (
    aceitar_substituicao,
    propor_substituicao,
    rejeitar_substituicao,
)
from backend.app.services.critico.auditor_service import (
    ResumoAuditoria,
    auditar_banco,
    montar_resumo,
)
from backend.app.services.geracao.banco_service import Produzida
from backend.app.services.provedor.provedor_service import ProvedorLLMService
from backend.app.services.rag.embeddings import Embeddings, get_embeddings
from backend.app.services.rag.rerank import Reranker, get_reranker

router = APIRouter(prefix="/bancos/{banco_id}", tags=["Controle do Banco"])


@router.get("", response_model=BancoResposta)
def ler(
    banco_id: int,
    de: int = Query(1, ge=1, description="Primeiro número do bloco."),
    ate: int = Query(20, ge=1, description="Último número do bloco."),
    com_gabarito: bool = Query(False, description="só com pedido explícito."),
    incluir_historico: bool = Query(
        False, description="Mostra também substituídas, candidatas e descartadas."
    ),
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> BancoLido:
    if ate < de:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"ate ({ate}) não pode ser menor que de ({de}).",
        )
    return ler_banco(db, docente, banco_id, de, ate, com_gabarito, incluir_historico)


@router.get("/relatorios", response_model=list[RelatorioImpactoResposta])
def relatorios(
    banco_id: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> list[RelatorioImpacto]:
    return listar_relatorios(db, docente, banco_id)


@router.post("/exclusoes", response_model=RelatorioImpactoResposta)
def excluir(
    banco_id: int,
    dados: ExclusaoCriar,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> RelatorioImpacto:
    banco = obter_banco(db, docente, banco_id)
    return excluir_questoes(db, docente, banco, dados.numeros, dados.revisao_esperada)


@router.post("/congelar", response_model=RelatorioImpactoResposta)
def congelar(
    banco_id: int,
    dados: ComandoRevisao,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> RelatorioImpacto:
    banco = obter_banco(db, docente, banco_id)
    return congelar_banco(db, docente, banco, dados.revisao_esperada)


@router.post(
    "/questoes/{numero}/substituicao",
    response_model=PropostaSubstituicaoResposta,
    status_code=status.HTTP_201_CREATED,
)
def propor(
    banco_id: int,
    numero: int,
    resposta: Response,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
    embeddings: Embeddings = Depends(get_embeddings),
    reranker: Reranker = Depends(get_reranker),
    provedor: ProvedorLLMService = Depends(get_provedor),
) -> PropostaSubstituicaoResposta:
    # Chamada longa: ~38 s (geração + revisão). Nada muda no banco até o docente
    # aceitar.
    banco = obter_banco(db, docente, banco_id)
    produzida = propor_substituicao(
        db, embeddings, reranker, provedor, docente, banco, numero
    )
    if isinstance(produzida, Produzida):
        return PropostaSubstituicaoResposta(
            numero=numero,
            candidata=QuestaoResposta.model_validate(
                questao_lida(produzida.questao, com_gabarito=True)
            ),
        )
    # Insuficiência de fonte não é erro: é funcionando, e nada foi
    # criado — então 200, não 201.
    resposta.status_code = status.HTTP_200_OK
    return PropostaSubstituicaoResposta(
        numero=numero,
        motivo_insuficiencia=produzida.motivo,
        localizacao=produzida.localizacao,
    )


@router.post(
    "/questoes/{numero}/substituicao/aceitar", response_model=RelatorioImpactoResposta
)
def aceitar(
    banco_id: int,
    numero: int,
    dados: ComandoRevisao,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> RelatorioImpacto:
    banco = obter_banco(db, docente, banco_id)
    return aceitar_substituicao(db, docente, banco, numero, dados.revisao_esperada)


@router.post(
    "/questoes/{numero}/substituicao/rejeitar", response_model=RejeicaoResposta
)
def rejeitar(
    banco_id: int,
    numero: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> RejeicaoResposta:
    banco = obter_banco(db, docente, banco_id)
    rejeitar_substituicao(db, docente, banco, numero)
    return RejeicaoResposta(numero=numero)


@router.post("/auditoria", response_model=ResumoAuditoriaResposta)
def auditar(
    banco_id: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
    embeddings: Embeddings = Depends(get_embeddings),
    reranker: Reranker = Depends(get_reranker),
    provedor: ProvedorLLMService = Depends(get_provedor),
) -> ResumoAuditoria:
    # Chamada longa: ~19 s por questão mais o retrieval. O commit por questão do
    # auditor_service é o que torna um timeout de proxy não destrutivo — a
    # chamada seguinte retoma de onde parou.
    #
    # Sem `revisao_esperada`: auditar não muda o banco, então não há estado a
    # proteger. Mesma razão pela qual `rejeitar_substituicao` não a exige.
    banco = obter_banco(db, docente, banco_id)
    return auditar_banco(db, embeddings, reranker, provedor, docente, banco)


@router.get("/auditoria", response_model=ResumoAuditoriaResposta)
def ler_auditoria(
    banco_id: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> ResumoAuditoria:
    """Achados da revisão atual. Banco nunca auditado devolve resumo vazio, não
    404: ausência de auditoria não é ausência de banco."""
    banco = obter_banco(db, docente, banco_id)
    return montar_resumo(db, banco)
