"""Banco de teste sintético, com defeitos conhecidos e anotados.

O critério de aceitação é "identifica ≥ 90% dos problemas detectados
em banco de teste sintético". Este módulo é esse banco, versionado, para que a
medição seja repetível e o número citado no TCC tenha origem verificável.

A parte determinística (`assimetria_forma`) é conferida automaticamente pelo
`test_auditor_sintetico.py`. A parte semântica NÃO é: com duplo de provedor, a
taxa sairia do roteiro do fake e não do modelo, e citá-la como ≥90% seria falso.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.domain import (
    FaixaDificuldade,
    FormatoItem,
    NivelBloom,
    RiscoAuditoria,
    TipoQuestao,
)
from backend.app.models.banco import (
    Alternativa,
    BancoQuestoes,
    FonteInterna,
    JustificativaEstruturada,
    Questao,
    RevisaoQuestao,
)
from backend.app.models.identidade import SessaoGeracao
from backend.app.models.materiais import ChunkMaterial
from backend.tests.fabrica_banco import criar_banco, criar_material_minimo

# Trechos do "material". São eles que tornam os defeitos semânticos reais: sem
# um trecho que sustente o distrator, `correta_nao_unica` seria opinião.
TRECHOS = [
    (
        "página 1",
        (
            "A busca em largura (BFS) usa uma fila para visitar os vértices por "
            "camadas de distância crescente a partir da origem."
        ),
    ),
    (
        "página 2",
        (
            "A busca em profundidade (DFS) usa uma pilha, explícita ou a pilha de "
            "recursão, e desce o máximo possível antes de retroceder."
        ),
    ),
    (
        "página 3",
        (
            "Em um grafo não ponderado, a BFS encontra o caminho mínimo em número "
            "de arestas. Em grafos ponderados isso não vale, e usa-se Dijkstra."
        ),
    ),
    (
        "página 4",
        (
            "A ordenação topológica pode ser obtida por DFS, empilhando cada "
            "vértice ao terminar de visitá-lo, ou pelo algoritmo de Kahn com uma "
            "fila de vértices de grau de entrada zero."
        ),
    ),
]


@dataclass(frozen=True)
class DefeitoEsperado:
    numero: int
    risco: RiscoAuditoria
    alvo: str
    por_que: str


# O gabarito da medição. Cada linha é um problema que a auditoria DEVE achar.
DEFEITOS_ESPERADOS = (
    DefeitoEsperado(
        numero=1,
        risco=RiscoAuditoria.CORRETA_NAO_UNICA,
        alvo="B",
        por_que=(
            "A questão pergunta o que obtém ordenação topológica e marca DFS "
            "como única correta, mas a página 4 sustenta Kahn com fila do mesmo "
            "jeito. B é defensável."
        ),
    ),
    DefeitoEsperado(
        numero=2,
        risco=RiscoAuditoria.DISTRATOR_INDEFENSAVEL,
        alvo="D",
        por_que=(
            "'O grafo deixa de existir' é absurda e fora do domínio: o aluno a "
            "elimina sem saber nada de BFS."
        ),
    ),
    DefeitoEsperado(
        numero=3,
        risco=RiscoAuditoria.ASSIMETRIA_FORMA,
        alvo="A",
        por_que=(
            "A correta tem 26 palavras e a errada mais longa tem 2: forma "
            "entrega a resposta. Medido sem LLM."
        ),
    ),
    DefeitoEsperado(
        numero=4,
        risco=RiscoAuditoria.CORRETA_NAO_UNICA,
        alvo="C",
        por_que=(
            "A questão afirma caminho mínimo por BFS sem dizer 'não ponderado'; "
            "a página 3 sustenta Dijkstra como resposta igualmente correta."
        ),
    ),
    DefeitoEsperado(
        numero=4,
        risco=RiscoAuditoria.DISTRATOR_INDEFENSAVEL,
        alvo="E",
        por_que="'Nenhuma das anteriores' não é defensável nem mede conteúdo.",
    ),
    # A questão 5 não tem defeito, de propósito: achado nela é falso positivo, e
    # falso positivo também conta na avaliação da auditoria.
)

# (enunciado, [textos das 5 alternativas], letra correta)
_QUESTOES: tuple[tuple[str, list[str], str], ...] = (
    (
        "Qual técnica obtém uma ordenação topológica de um DAG?",
        [
            "Busca em profundidade, empilhando ao terminar cada vértice",
            "Algoritmo de Kahn com fila de grau de entrada zero",
            "Ordenação por inserção sobre os rótulos",
            "Multiplicação da matriz de adjacência",
            "Percurso em espiral a partir do centro",
        ],
        "A",
    ),
    (
        "Qual estrutura a busca em largura utiliza?",
        [
            "Uma fila",
            "Uma pilha",
            "Um vetor ordenado",
            "O grafo deixa de existir durante a busca",
            "Uma tabela de dispersão",
        ],
        "A",
    ),
    (
        "O que a busca em largura garante em um grafo não ponderado?",
        [
            (
                "Que o caminho encontrado entre a origem e cada vértice "
                "alcançável tem o menor número possível de arestas, porque a "
                "visita acontece por camadas de distância crescente a partir "
                "da origem"
            ),
            "Nada",
            "Ciclos",
            "Pesos",
            "Cortes",
        ],
        "A",
    ),
    (
        "Qual algoritmo encontra o caminho de custo mínimo em um grafo?",
        [
            "Busca em largura",
            "Busca em profundidade",
            "Dijkstra",
            "Ordenação topológica",
            "Nenhuma das anteriores",
        ],
        "A",
    ),
    (
        "Qual estrutura a busca em profundidade utiliza?",
        [
            "Uma pilha",
            "Uma fila",
            "Um vetor ordenado",
            "Uma tabela hash",
            "Uma árvore balanceada",
        ],
        "A",
    ),
)


def montar_banco_sintetico(db: Session, sessao: SessaoGeracao) -> BancoQuestoes:
    """Material indexado, banco de 5 objetivas e os defeitos de DEFEITOS_ESPERADOS.

    O vetor de embedding é o mesmo para todos os chunks de propósito: quem decide
    quais trechos chegam é o `EmbeddingsFake`/`RerankerFake` na suíte, e o Ollama
    de verdade na medição manual.
    """
    material = criar_material_minimo(db, sessao, "P1")
    for ordem, (localizacao, texto) in enumerate(TRECHOS):
        db.add(
            ChunkMaterial(
                material_id=material.id,
                ordem=ordem,
                texto=texto,
                localizacao=localizacao,
                vetor_embedding=[0.0] * 1023 + [1.0],
            )
        )
    db.flush()

    banco = criar_banco(db, sessao, n_objetivas=len(_QUESTOES))
    for numero, (enunciado, textos, correta) in enumerate(_QUESTOES, start=1):
        questao = Questao(
            banco_id=banco.id,
            numero=numero,
            tipo=TipoQuestao.OBJETIVA,
            formato=FormatoItem.PROPOSICAO,
            enunciado=enunciado,
            nivel_bloom=NivelBloom.ENTENDER,
            faixa_dificuldade=FaixaDificuldade.MEDIA,
            tema="Grafos",
        )
        db.add(questao)
        db.flush()
        db.add(
            FonteInterna(
                questao_id=questao.id,
                material_id=material.id,
                localizacao=TRECHOS[0][0],
                trecho_base=TRECHOS[0][1],
            )
        )
        for indice, (letra, texto) in enumerate(zip("ABCDE", textos, strict=True)):
            db.add(
                Alternativa(
                    questao_id=questao.id,
                    letra=letra,
                    texto=texto,
                    correta=letra == correta,
                    e_gemeo_malvado=indice == 1,
                )
            )
        db.add(
            JustificativaEstruturada(
                questao_id=questao.id,
                objetivo_cognitivo="identificar a estrutura ou técnica correta",
                justificativa_correta="sustentada pelo trecho citado",
                invalidacao_distratores=[f"distrator {i}" for i in range(4)],
                verificacao_unicidade=True,
                texto_verificacao_unicidade="declarada única pelo gerador",
            )
        )
        db.add(
            RevisaoQuestao(
                questao_id=questao.id,
                rascunho={"enunciado": enunciado},
                violacoes_rascunho=[],
                violacoes_final=[],
                modelo_geracao="sintetico",
                modelo_revisao="sintetico",
            )
        )
        banco.n_atual += 1
    db.commit()
    return banco
