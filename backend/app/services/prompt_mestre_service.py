"""Versionamento do prompt mestre — Núcleo Determinístico, nunca chama LLM.

O texto vive em git; o banco guarda qual versão está ativa e qual foi o texto
exato montado, para auditoria. Registrar uma versão nunca a ativa: separar os
dois atos é o que torna o rollback um ato deliberado.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.domain import TipoQuestao
from backend.app.exceptions import (
    NenhumPromptAtivoException,
    PromptDivergenteException,
    VersaoPromptDuplicadaException,
    VersaoPromptNaoEncontradaException,
)
from backend.app.models.prompt_provedor import PromptMestre
from backend.app.prompt.montagem import (
    DIRETORIO_MODULOS,
    calcular_hash,
    carregar_modulos_versionados,
    montar_sistema,
    montar_sistema_critico,
)
from backend.app.prompt.parametros import ParametrosGeracao


def registrar_versao(
    db: Session, versao: str, papel_definido: str, params: ParametrosGeracao
) -> PromptMestre:
    if db.scalar(select(PromptMestre).where(PromptMestre.versao == versao)):
        raise VersaoPromptDuplicadaException(versao)

    prompt = PromptMestre(
        versao=versao,
        conteudo=montar_sistema(TipoQuestao.OBJETIVA, params),
        conteudo_critico=montar_sistema_critico(TipoQuestao.OBJETIVA, params),
        conteudo_discursiva=montar_sistema(TipoQuestao.DISCURSIVA, params),
        conteudo_critico_discursiva=montar_sistema_critico(
            TipoQuestao.DISCURSIVA, params
        ),
        papel_definido=papel_definido,
        hash_modulos=calcular_hash(carregar_modulos_versionados()),
        # Nasce inativa de propósito: ativar é ato separado.
        ativo=False,
    )
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return prompt


def listar_versoes(db: Session) -> list[PromptMestre]:
    """Histórico consultável, mais recente primeiro."""
    return list(
        db.scalars(
            select(PromptMestre).order_by(
                PromptMestre.criado_em.desc(), PromptMestre.id.desc()
            )
        )
    )


def obter_ativo(db: Session) -> PromptMestre:
    prompt = db.scalar(select(PromptMestre).where(PromptMestre.ativo.is_(True)))
    if prompt is None:
        raise NenhumPromptAtivoException()
    return prompt


def ativar(db: Session, versao: str) -> PromptMestre:
    """Rollback. Desativa a anterior e ativa a pedida na mesma
    transação — duas versões ativas tornariam indefinido o que foi enviado."""
    alvo = db.scalar(select(PromptMestre).where(PromptMestre.versao == versao))
    if alvo is None:
        raise VersaoPromptNaoEncontradaException(versao)

    for prompt in db.scalars(
        select(PromptMestre).where(
            PromptMestre.ativo.is_(True), PromptMestre.id != alvo.id
        )
    ):
        prompt.ativo = False
    alvo.ativo = True
    db.commit()
    db.refresh(alvo)
    return alvo


@lru_cache(maxsize=1)
def _hash_por_assinatura(assinatura: tuple) -> str:
    return calcular_hash(carregar_modulos_versionados())


def _hash_em_disco() -> str:
    """O hash só é recalculado quando algum .md muda de mtime, tamanho ou
    nome — cada geração, auditoria e substituição passa por aqui, e reler e
    refazer o SHA de todos os módulos a cada uma era desperdício.
    Edição que preserva mtime e tamanho passa despercebida até o
    reinício do processo; troque a assinatura por hash de conteúdo se importar."""
    assinatura = tuple(
        (str(c), (st := c.stat()).st_mtime_ns, st.st_size)
        for c in sorted(DIRETORIO_MODULOS.rglob("*.md"))
    )
    return _hash_por_assinatura(assinatura)


def verificar_integridade(db: Session) -> None:
    """Os módulos em disco mudaram sem versão nova? Então `conteudo` descreve
    algo que não seria mais enviado, e a auditoria passa a mentir."""
    ativo = obter_ativo(db)
    em_disco = _hash_em_disco()
    if ativo.hash_modulos != em_disco:
        raise PromptDivergenteException(gravado=ativo.hash_modulos, em_disco=em_disco)
