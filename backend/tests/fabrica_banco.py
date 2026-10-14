"""Banco e questões montados direto no banco de dados, sem LLM.

 testa exclusão, congelamento, consistência e leitura sobre bancos
já prontos. Gerar essas questões pelo laço custaria duas respostas
de roteiro por questão e amarraria cada teste ao duplo do provedor.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.domain import (
    EstadoBanco,
    EstadoQuestao,
    FaixaDificuldade,
    FormatoItem,
    FormatoArquivo,
    NivelBloom,
    OrigemTexto,
    StatusLegibilidade,
    TipoMaterial,
    TipoQuestao,
)
from backend.app.models.banco import (
    Alternativa,
    AspectoEsperado,
    BancoQuestoes,
    FonteInterna,
    JustificativaEstruturada,
    Questao,
    RevisaoQuestao,
)
from backend.app.models.identidade import SessaoGeracao
from backend.app.models.materiais import MaterialReferencia
from backend.app.schemas.geracao import LETRAS


def criar_banco(
    db: Session,
    sessao: SessaoGeracao,
    *,
    versao: str = "v1",
    n_objetivas: int = 0,
    n_discursivas: int = 0,
    estado: EstadoBanco = EstadoBanco.ABERTO,
) -> BancoQuestoes:
    banco = BancoQuestoes(
        sessao_id=sessao.id,
        versao=versao,
        estado=estado,
        n_alvo=n_objetivas + n_discursivas,
        n_alvo_objetivas=n_objetivas,
        n_alvo_discursivas=n_discursivas,
        n_atual=0,
    )
    db.add(banco)
    db.flush()
    return banco


def criar_material_minimo(
    db: Session, sessao: SessaoGeracao, identificador: str = "P1"
) -> MaterialReferencia:
    """Só o que a FK de FonteInterna exige. Nada é escrito no armazenamento:
    estes testes nunca leem o arquivo. Reusa o material da sessão com o mesmo
    identificador: hash e identificador são únicos por sessão."""
    existente = (
        db.query(MaterialReferencia)
        .filter_by(sessao_id=sessao.id, identificador_curto=identificador)
        .first()
    )
    if existente is not None:
        return existente
    material = MaterialReferencia(
        sessao_id=sessao.id,
        identificador_curto=identificador,
        nome_arquivo=f"{identificador}.pdf",
        tipo=TipoMaterial.PDF,
        formato=FormatoArquivo.PDF,
        status_legibilidade=StatusLegibilidade.LEGIVEL,
        chave_armazenamento=f"{sessao.id}/{identificador}.pdf",
        chave_texto_extraido=f"{sessao.id}/{identificador}.txt",
        hash_sha256=identificador.ljust(64, "0"),
        tamanho_bytes=1024,
        origem_texto=OrigemTexto.NATIVO,
    )
    db.add(material)
    db.flush()
    return material


def _fonte(db: Session, questao: Questao, material: MaterialReferencia) -> FonteInterna:
    fonte = FonteInterna(
        questao_id=questao.id,
        material_id=material.id,
        localizacao=f"página {questao.numero}",
        trecho_base=f"trecho que sustenta a questão {questao.numero}",
    )
    db.add(fonte)
    db.flush()
    return fonte


def criar_questao_objetiva(
    db: Session,
    banco: BancoQuestoes,
    *,
    numero: int,
    faixa: FaixaDificuldade = FaixaDificuldade.MEDIA,
    estado: EstadoQuestao = EstadoQuestao.ATIVA,
    material: MaterialReferencia | None = None,
    k: int | None = None,
    violacoes_final: list[dict] | None = None,
    subtema: str | None = "Busca em largura",
    invalidacoes_ligadas: bool = True,
) -> Questao:
    """Questão coerente segundo `verificar_consistencia`. Os testes de
    inconsistência partem desta e estragam um campo por vez."""
    k = k if k is not None else banco.sessao.k_alternativas
    material = material or criar_material_minimo(db, banco.sessao)
    questao = Questao(
        banco_id=banco.id,
        numero=numero,
        tipo=TipoQuestao.OBJETIVA,
        formato=FormatoItem.PROPOSICAO,
        enunciado=f"Questão {numero}: qual estrutura a busca em largura usa?",
        nivel_bloom=NivelBloom.APLICAR,
        faixa_dificuldade=faixa,
        tema="Grafos",
        subtema=subtema,
        estado=estado,
    )
    db.add(questao)
    db.flush()
    _fonte(db, questao, material)
    for i, letra in enumerate(LETRAS[:k]):
        db.add(
            Alternativa(
                questao_id=questao.id,
                letra=letra,
                texto=f"opção {letra}",
                correta=i == 0,
                e_gemeo_malvado=i == 1,
            )
        )
    db.add(
        JustificativaEstruturada(
            questao_id=questao.id,
            objetivo_cognitivo="identificar a estrutura",
            justificativa_correta="o trecho afirma o uso de fila",
            # A correta é sempre a A (i == 0 acima). False reproduz banco
            # anterior à, com a lista sem letra.
            invalidacao_distratores=(
                [
                    {"letra": LETRAS[i], "motivo": f"distrator {LETRAS[i]}"}
                    for i in range(1, k)
                ]
                if invalidacoes_ligadas
                else [f"distrator {i}" for i in range(k - 1)]
            ),
            verificacao_unicidade=True,
            texto_verificacao_unicidade="nenhuma errada é defensável",
        )
    )
    db.add(
        RevisaoQuestao(
            questao_id=questao.id,
            rascunho={"enunciado": "rascunho que nunca deve vazar na resposta"},
            violacoes_rascunho=[],
            violacoes_final=violacoes_final or [],
            modelo_geracao="fake",
            modelo_revisao="fake",
        )
    )
    if estado is EstadoQuestao.ATIVA:
        banco.n_atual += 1
    db.flush()
    return questao


def criar_questao_discursiva(
    db: Session,
    banco: BancoQuestoes,
    *,
    numero: int,
    faixa: FaixaDificuldade = FaixaDificuldade.MEDIA,
    estado: EstadoQuestao = EstadoQuestao.ATIVA,
    material: MaterialReferencia | None = None,
    aspectos: int = 2,
    subtema: str | None = "Busca em largura",
) -> Questao:
    material = material or criar_material_minimo(db, banco.sessao)
    questao = Questao(
        banco_id=banco.id,
        numero=numero,
        tipo=TipoQuestao.DISCURSIVA,
        formato=FormatoItem.PROPOSICAO,
        enunciado=f"Questão {numero}: explique por que a busca em largura usa fila.",
        nivel_bloom=NivelBloom.ENTENDER,
        faixa_dificuldade=faixa,
        tema="Grafos",
        subtema=subtema,
        estado=estado,
    )
    db.add(questao)
    db.flush()
    fonte = _fonte(db, questao, material)
    for ordem in range(1, aspectos + 1):
        db.add(
            AspectoEsperado(
                questao_id=questao.id,
                ordem=ordem,
                texto=f"aspecto {ordem} esperado na resposta",
                fonte_interna_id=fonte.id,
            )
        )
    db.add(
        JustificativaEstruturada(
            questao_id=questao.id,
            objetivo_cognitivo="explicar a estrutura auxiliar",
        )
    )
    db.add(
        RevisaoQuestao(
            questao_id=questao.id,
            rascunho={"enunciado": "rascunho que nunca deve vazar na resposta"},
            violacoes_rascunho=[],
            violacoes_final=[],
            modelo_geracao="fake",
            modelo_revisao="fake",
        )
    )
    if estado is EstadoQuestao.ATIVA:
        banco.n_atual += 1
    db.flush()
    return questao
