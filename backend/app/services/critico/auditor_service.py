"""Agente Crítico, auditoria sob comando —.

Parte B do mesmo agente da `agente_critico_service`. Duas metades por questão:
o Núcleo Determinístico remede as duas regras de assimetria sobre a `Questao`
persistida, e o Núcleo Semântico julga unicidade da correta e defensabilidade
dos distratores.

Auditar não muda nada. A única escrita desta etapa é `INSERT` em
`registros_auditoria`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.domain import (
    EstadoQuestao,
    RegraQualidade,
    RiscoAuditoria,
    TipoEventoAuditoria,
    TipoQuestao,
)
from backend.app.models.auditoria import RegistroAuditoria
from backend.app.models.banco import BancoQuestoes, Questao
from backend.app.models.identidade import Docente, SessaoGeracao
from backend.app.prompt.montagem import montar_sistema_auditor
from backend.app.schemas.auditoria import montar_schema_auditoria
from backend.app.services.calculo_distribuicao_service import (
    DistribuicaoQuestoes,
    calcular_distribuicao,
)
from backend.app.services.controle_banco.consistencia import verificar_consistencia
from backend.app.services.geracao.contexto import formatar_trechos, parametros_da_sessao
from backend.app.services.log_auditoria import registrar_evento
from backend.app.services.prompt_mestre_service import (
    obter_ativo,
    verificar_integridade,
)
from backend.app.services.provedor.tipos import RequisicaoLLM
from backend.app.services.qualidade.validador_itens import (
    AlternativaAvaliavel,
    ItemObjetivo,
    validar_objetiva,
)
from backend.app.services.rag.retrieval_service import TrechoRecuperado, buscar

# Das seis regras que `validar_objetiva` devolve, só estas duas são o que o
# chama de "assimetria de forma ou extensão". As outras quatro
# (termo_absoluto, mencao_fonte, gemeos_insuficientes, gemeo_na_correta) são
# e já apareceram na geração.
_REGRAS_DE_ASSIMETRIA = (
    RegraQualidade.TAMANHO_ALTERNATIVA,
    RegraQualidade.CORRETA_LONGA,
)

_INSTRUCAO_POR_REGRA = {
    RegraQualidade.TAMANHO_ALTERNATIVA: (
        "aproxime o tamanho dessa alternativa do das demais"
    ),
    RegraQualidade.CORRETA_LONGA: (
        "encurte a correta ou alongue as erradas até os tamanhos se aproximarem"
    ),
}


@dataclass(frozen=True)
class Achado:
    risco: RiscoAuditoria
    # Sempre uma letra: as duas regras de forma usadas aqui apontam alternativa,
    # e o modelo só pode emitir letra (Literal no schema).
    alvo: str
    localizacao: str | None  # None nos achados de forma
    trecho_fonte: str | None  # None nos achados de forma
    proposta_ajuste: str

    def como_dict(self) -> dict[str, str | None]:
        return {
            "risco": self.risco.value,
            "alvo": self.alvo,
            "localizacao": self.localizacao,
            "trecho_fonte": self.trecho_fonte,
            "proposta_ajuste": self.proposta_ajuste,
        }


def item_de_questao(questao: Questao, trechos: list[TrechoRecuperado]) -> ItemObjetivo:
    """Mesma forma de `item_objetivo_de` da parte A, lendo do ORM em vez da
    saída do modelo. É o uso que o docstring de `validador_itens` já previa."""
    return ItemObjetivo(
        enunciado=questao.enunciado,
        alternativas=[
            AlternativaAvaliavel(
                letra=alternativa.letra,
                texto=alternativa.texto,
                correta=alternativa.correta,
                e_gemeo_malvado=alternativa.e_gemeo_malvado,
            )
            for alternativa in sorted(questao.alternativas, key=lambda a: a.letra)
        ],
        trechos_base=[fonte.trecho_base for fonte in questao.fontes_internas],
        # Dos trechos RECUPERADOS, não das fontes gravadas: é contra eles que a
        # regra de menção de fonte compara.
        identificadores_fonte=sorted({t.identificador_curto for t in trechos}),
    )


def achados_de_forma(item: ItemObjetivo) -> list[Achado]:
    """Assimetria de forma ou extensão, medida sem LLM.

    A proposta carrega o `detalhe` da violação, que já diz o que foi medido — é
    o "risco identificado" que pede, sem um campo a mais.
    """
    return [
        Achado(
            risco=RiscoAuditoria.ASSIMETRIA_FORMA,
            alvo=violacao.alvo,
            # Assimetria não é concorrência de fonte: forçar um trecho aqui
            # seria inventar rastreabilidade.
            localizacao=None,
            trecho_fonte=None,
            proposta_ajuste=(
                f"{violacao.detalhe} — {_INSTRUCAO_POR_REGRA[violacao.regra]}."
            ),
        )
        for violacao in validar_objetiva(item)
        if violacao.regra in _REGRAS_DE_ASSIMETRIA
    ]


@dataclass(frozen=True)
class AuditoriaQuestao:
    achados: list[Achado]
    # Qual modelo respondeu: o fallback pode trocar entre chamadas, e isso muda
    # a leitura da métrica.
    modelo: str
    # As localizações enviadas, para o payload permitir conferir a citação.
    localizacoes: list[str]


def _montar_usuario(questao: Questao, trechos: list[TrechoRecuperado]) -> str:
    alternativas = sorted(questao.alternativas, key=lambda a: a.letra)
    correta = next((a.letra for a in alternativas if a.correta), "?")
    # A correta aparece duas vezes, marcada na linha e declarada no fim. É
    # redundância deliberada: é o dado sem o qual o modelo não pode julgar
    # unicidade, e não vale economizar tokens nele.
    linhas = [
        f"{a.letra}) {a.texto}" + ("   <- CORRETA" if a.correta else "")
        for a in alternativas
    ]
    return (
        "Trechos disponíveis:\n"
        + formatar_trechos(trechos)
        + f"\n\nQuestão {questao.numero}\nEnunciado: {questao.enunciado}\n"
        + "\n".join(linhas)
        + f"\n\nAlternativa correta: {correta}"
        + "\n\nAudite esta questão e devolva os achados. Lista vazia se não "
        "houver problema."
    )


def auditar_questao(
    db: Session,
    embeddings,
    reranker,
    provedor,
    sessao: SessaoGeracao,
    questao: Questao,
    distribuicao: DistribuicaoQuestoes,
) -> AuditoriaQuestao:
    # O enunciado É a consulta: se um distrator é defensável por um trecho que a
    # questão não cita, só o retrieval o encontra. `buscar` já restringe aos
    # materiais da sessão (R2).
    trechos = buscar(
        db,
        embeddings,
        reranker,
        sessao,
        questao.enunciado,
        k=settings.rag_top_k,
        candidatos=settings.rag_candidatos,
    )
    localizacoes = [t.localizacao for t in trechos]

    achados = achados_de_forma(item_de_questao(questao, trechos))

    resposta = provedor.gerar(
        sessao.id,
        RequisicaoLLM(
            sistema=montar_sistema_auditor(parametros_da_sessao(sessao, distribuicao)),
            usuario=_montar_usuario(questao, trechos),
            formato=montar_schema_auditoria(len(questao.alternativas), localizacoes),
            temperatura=settings.auditoria_temperatura,
            max_tokens=settings.auditoria_max_tokens,
        ),
    )

    achados.extend(
        Achado(
            risco=RiscoAuditoria(gerado.risco),
            alvo=gerado.alvo,
            localizacao=gerado.localizacao,
            trecho_fonte=gerado.trecho_fonte,
            proposta_ajuste=gerado.proposta_ajuste,
        )
        for gerado in sorted(resposta.conteudo.achados, key=lambda a: a.alvo)
    )
    return AuditoriaQuestao(
        achados=achados,
        modelo=resposta.modelo,
        # Deduplicada aqui também, para o payload dizer o mesmo que o schema
        # aceitou.
        localizacoes=list(dict.fromkeys(localizacoes)),
    )


# Discriminador do evento em `registros_auditoria`. vai usar a mesma
# tabela para o log transversal de comandos, com outro tipo_evento — é o que
# permite as duas coisas conviverem sem tabela nova.
TIPO_EVENTO_AUDITORIA = TipoEventoAuditoria.AUDITORIA_QUESTAO.value

_DUAS_CASAS = Decimal("0.01")


@dataclass(frozen=True)
class QuestaoAuditada:
    numero: int
    achados: list[Achado]


@dataclass(frozen=True)
class ResumoAuditoria:
    banco_id: int
    revisao_auditada: int
    auditadas: int
    ja_auditadas: int
    discursivas_ignoradas: int
    # Só as questões COM achado: relatório lista item problemático.
    questoes: list[QuestaoAuditada]
    proporcao_com_achado: Decimal


def _ativas_por_tipo(db: Session, banco: BancoQuestoes) -> tuple[list[Questao], int]:
    """Objetivas ativas em ordem de número, e quantas discursivas ativas ficaram
    de fora. Excluída, substituída, candidata e descartada não estão no banco."""
    ativas = list(
        db.scalars(
            select(Questao)
            .where(
                Questao.banco_id == banco.id,
                Questao.estado == EstadoQuestao.ATIVA,
            )
            .order_by(Questao.numero, Questao.id)
        )
    )
    objetivas = [q for q in ativas if q.tipo is TipoQuestao.OBJETIVA]
    return objetivas, len(ativas) - len(objetivas)


def _payloads_da_revisao(
    db: Session, banco: BancoQuestoes, objetivas: list[Questao]
) -> list[dict]:
    """Registros desta revisão. Filtra por `entidade_afetada` das questões do
    banco e confere a revisão em Python: evita cast de JSONB no SQL, e a lista
    de entidades é pequena (no máximo 25)."""
    if not objetivas:
        return []
    entidades = {f"questoes:{q.id}" for q in objetivas}
    payloads = db.scalars(
        select(RegistroAuditoria.payload).where(
            RegistroAuditoria.tipo_evento == TIPO_EVENTO_AUDITORIA,
            RegistroAuditoria.entidade_afetada.in_(entidades),
        )
    )
    return [p for p in payloads if p.get("revisao_auditada") == banco.revisao]


def _achado_de_dict(dados: dict) -> Achado:
    return Achado(
        risco=RiscoAuditoria(dados["risco"]),
        alvo=dados["alvo"],
        localizacao=dados["localizacao"],
        trecho_fonte=dados["trecho_fonte"],
        proposta_ajuste=dados["proposta_ajuste"],
    )


def _proporcao(com_achado: int, auditadas: int) -> Decimal:
    if auditadas == 0:
        return Decimal("0.00")
    return (Decimal(100 * com_achado) / Decimal(auditadas)).quantize(
        _DUAS_CASAS, rounding=ROUND_HALF_EVEN
    )


def montar_resumo(
    db: Session, banco: BancoQuestoes, ja_antes: int | None = None
) -> ResumoAuditoria:
    """Lê `registros_auditoria` e monta o resumo. Usada pelo POST, depois do
    laço, e pelo GET: um construtor só garante que os dois verbos não divirjam.

    `ja_antes=None` significa "nenhuma chamada aconteceu" — é o caso do GET, e
    então `ja_auditadas` é igual a `auditadas`.
    """
    objetivas, discursivas = _ativas_por_tipo(db, banco)
    payloads = _payloads_da_revisao(db, banco, objetivas)
    com_achado = [
        QuestaoAuditada(
            numero=payload["numero"],
            achados=[_achado_de_dict(a) for a in payload["achados"]],
        )
        for payload in sorted(payloads, key=lambda p: p["numero"])
        if payload["achados"]
    ]
    auditadas = len(payloads)
    return ResumoAuditoria(
        banco_id=banco.id,
        revisao_auditada=banco.revisao,
        auditadas=auditadas,
        ja_auditadas=auditadas if ja_antes is None else ja_antes,
        discursivas_ignoradas=discursivas,
        questoes=com_achado,
        # Sobre todas as auditadas nesta revisão, não só as desta chamada: com
        # retomada, `auditadas` desta chamada pode ser 0 e a proporção continua
        # sendo a do banco.
        proporcao_com_achado=_proporcao(len(com_achado), auditadas),
    )


def _numeros_ja_auditados(
    db: Session, banco: BancoQuestoes, objetivas: list[Questao]
) -> set[int]:
    return {p["numero"] for p in _payloads_da_revisao(db, banco, objetivas)}


def auditar_banco(
    db: Session,
    embeddings,
    reranker,
    provedor,
    docente: Docente,
    banco: BancoQuestoes,
) -> ResumoAuditoria:
    """Roda com o banco aberto ou congelado: auditoria é leitura.

    Não muda estado, não incrementa revisão, não gera RelatorioImpacto. A única
    escrita é INSERT em registros_auditoria.
    """
    # Verificações baratas primeiro: descobrir divergência de prompt no minuto 7
    # desperdiçaria minutos de GPU.
    verificar_integridade(db)
    verificar_consistencia(db, banco)

    objetivas, _ = _ativas_por_tipo(db, banco)
    ja_auditados = _numeros_ja_auditados(db, banco, objetivas)
    if not objetivas:
        return montar_resumo(db, banco, ja_antes=0)

    prompt = obter_ativo(db)
    sessao = banco.sessao
    # O prompt não usa as contagens, mas ParametrosGeracao as pede; inventar
    # zeros faria o `conteudo` gravado divergir do enviado.
    distribuicao = calcular_distribuicao(
        banco.n_alvo_objetivas, sessao.p_f, sessao.p_m, sessao.p_d
    )

    for questao in objetivas:
        if questao.numero in ja_auditados:
            continue
        resultado = auditar_questao(
            db, embeddings, reranker, provedor, sessao, questao, distribuicao
        )
        registrar_evento(
            db,
            TipoEventoAuditoria.AUDITORIA_QUESTAO,
            f"questoes:{questao.id}",
            docente.id,
            {
                "banco_id": banco.id,
                "numero": questao.numero,
                "revisao_auditada": banco.revisao,
                "modelo": resultado.modelo,
                "versao_prompt": prompt.versao,
                "hash_modulos": prompt.hash_modulos,
                "localizacoes_enviadas": resultado.localizacoes,
                "achados": [a.como_dict() for a in resultado.achados],
            },
        )
        # Commit por questão: ~19 s mais retrieval por item, e falha no item 20
        # preserva os 19 anteriores. Mesmo padrão.
        db.commit()

    return montar_resumo(db, banco, ja_antes=len(ja_auditados))
