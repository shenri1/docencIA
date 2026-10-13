"""Controle do banco.

Atenção: `endpoints/banco.py` é outro arquivo, com prefixo `/sessoes/{sessao_id}`
e a rota de geração. Conferir o prefixo antes de acrescentar rota aqui.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_docente, get_provedor
from backend.app.core.db import get_db
from backend.app.core.storage import ArmazenamentoArquivos, get_armazenamento
from backend.app.models.banco import RelatorioImpacto
from backend.app.models.identidade import Docente
from backend.app.models.provas import ExportacaoDocx
from backend.app.schemas.banco import (
    N_MAXIMO_BANCO,
    BancoResposta,
    ComandoRevisao,
    ExclusaoCriar,
    ItemCatalogoResposta,
    PropostaSubstituicaoResposta,
    QuestaoResposta,
    RejeicaoResposta,
    RelatorioImpactoResposta,
    ResumoAuditoriaResposta,
)
from backend.app.schemas.exportacao import ExportacaoResposta
from backend.app.schemas.orientacao import DirecaoVariacao
from backend.app.schemas.prova import ProvasCriar, ProvasMontadasResposta
from backend.app.services.controle_banco.catalogo import ItemCatalogo, catalogar
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
from backend.app.services.exportacao.exportacao_service import (
    exportar,
    listar_exportacoes,
)
from backend.app.services.geracao.banco_service import Produzida
from backend.app.services.provas.leitura import provas_do_banco
from backend.app.services.provas.montagem_service import ProvasMontadas, montar_provas
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


@router.get("/catalogo", response_model=list[ItemCatalogoResposta])
def catalogo(
    banco_id: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> list[ItemCatalogo]:
    return catalogar(db, obter_banco(db, docente, banco_id))


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
    direcao: DirecaoVariacao | None = None,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
    embeddings: Embeddings = Depends(get_embeddings),
    reranker: Reranker = Depends(get_reranker),
    provedor: ProvedorLLMService = Depends(get_provedor),
) -> PropostaSubstituicaoResposta:
    # Chamada longa: ~38 s (geração + revisão). Nada muda no banco até o docente
    # aceitar. Com corpo, é a variação guiada.
    banco = obter_banco(db, docente, banco_id)
    produzida = propor_substituicao(
        db, embeddings, reranker, provedor, docente, banco, numero, direcao
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
    limite: int | None = Query(
        None,
        ge=1,
        le=N_MAXIMO_BANCO,
        description="Audita no máximo este tanto de questões nesta chamada. "
        "Sem limite, audita todas as pendentes.",
    ),
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
    embeddings: Embeddings = Depends(get_embeddings),
    reranker: Reranker = Depends(get_reranker),
    provedor: ProvedorLLMService = Depends(get_provedor),
) -> ResumoAuditoria:
    # Chamada longa: ~19 s por questão mais o retrieval. O commit por questão do
    # auditor_service é o que torna um timeout de proxy não destrutivo — a
    # chamada seguinte retoma de onde parou. O front chama com `limite` para
    # nenhuma requisição chegar perto do timeout.
    #
    # Sem `revisao_esperada`: auditar não muda o banco, então não há estado a
    # proteger. Mesma razão pela qual `rejeitar_substituicao` não a exige.
    banco = obter_banco(db, docente, banco_id)
    return auditar_banco(db, embeddings, reranker, provedor, docente, banco, limite)


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


@router.post(
    "/provas",
    response_model=ProvasMontadasResposta,
    status_code=status.HTTP_201_CREATED,
)
def montar(
    banco_id: int,
    dados: ProvasCriar,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> ProvasMontadas:
    # Uma chamada monta as DUAS provas: a regra de colisão de letras e a de
    # sobreposição de subtema são relações entre elas.
    banco = obter_banco(db, docente, banco_id)
    return montar_provas(
        db,
        docente,
        banco,
        n_objetivas=dados.n_objetivas,
        n_discursivas=dados.n_discursivas,
        revisao_esperada=dados.revisao_esperada,
    )


@router.get("/provas", response_model=ProvasMontadasResposta)
def ler_provas(
    banco_id: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> ProvasMontadas:
    """O mesmo que o POST devolveu, recalculado. 404 PROVAS_NAO_MONTADAS sem
    provas; o front só pergunta com o marco em M10 ou concluído."""
    banco = obter_banco(db, docente, banco_id)
    return provas_do_banco(db, banco)


@router.post(
    "/exportacoes",
    response_model=list[ExportacaoResposta],
    status_code=status.HTTP_201_CREATED,
)
def exportar_docx(
    banco_id: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
    armazenamento: ArmazenamentoArquivos = Depends(get_armazenamento),
) -> list[ExportacaoDocx]:
    # Os DOIS arquivos por chamada. Estado incoerente responde 409
    # INCONSISTENCIA_DE_ESTADO antes de qualquer escrita.
    banco = obter_banco(db, docente, banco_id)
    return exportar(db, docente, armazenamento, banco)


@router.get("/exportacoes", response_model=list[ExportacaoResposta])
def historico_exportacoes(
    banco_id: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> list[ExportacaoDocx]:
    return listar_exportacoes(db, docente, banco_id)
