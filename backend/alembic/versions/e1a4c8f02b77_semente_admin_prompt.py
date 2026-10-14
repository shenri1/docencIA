"""Semeia o primeiro administrador e o prompt mestre 1.0.0.

Uma instalação nova não conseguia gerar nada: gerar exige prompt mestre ativo,
registrar e ativar exige administrador, e o cadastro pela API só cria docente.
Esta migração fecha esse ciclo.

Administrador: vem de ADMIN_CREDENCIAL, ADMIN_NOME e ADMIN_SENHA (ver
.env.example). Sem os três, não cria ninguém e avisa — a senha nunca mora no
repositório. Credencial já cadastrada só é promovida se a senha da conta for a
ADMIN_SENHA — o cadastro é público, e quem registrasse antes a credencial do
administrador viraria administrador; senha diferente faz a migração falhar.
Senha fora da regra do cadastro também faz a migração falhar: configuração
errada não passa quieta.

Prompt: se não houver versão ativa, registra e ativa a 1.0.0 com os módulos em
disco. Disciplina e período do texto gravado são marcadores, porque a geração
reinjeta os parâmetros da sessão a cada chamada; o texto gravado é só o registro
de auditoria da versão.

Desvio declarado da convenção de migração: importa código do app
(`registrar_versao`, `ativar`, `hash_senha`), porque montar o prompt exige a
montagem do app. Se esse código mudar, esta semente muda junto.

Idempotente. `downgrade` é no-op: apagar o administrador ou o prompt poderia
apagar o que já foi usado.

Revision ID: e1a4c8f02b77
Revises: d8b3f6a2c914
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.security import hash_senha, verificar_senha
from backend.app.models.prompt_provedor import PromptMestre
from backend.app.prompt.parametros import ParametrosGeracao
from backend.app.schemas.identidade import DocenteCriar
from backend.app.services.prompt_mestre_service import ativar, registrar_versao

revision: str = "e1a4c8f02b77"
down_revision: str | None = "d8b3f6a2c914"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VERSAO_INICIAL = "1.0.0"
PAPEL_INICIAL = "docente universitário elaborador de questões"
PARAMETROS_MARCADORES = ParametrosGeracao(
    disciplina="(definida em cada sessão)",
    periodo="(definido em cada sessão)",
    area_do_conhecimento=None,
    tema_escopo=None,
    k_alternativas=5,
    n_faceis=0,
    n_medias=0,
    n_dificeis=0,
)


def _semear_admin(conexao: sa.Connection) -> None:
    credencial = settings.admin_credencial
    nome = settings.admin_nome
    senha = settings.admin_senha
    if not (credencial and nome and senha):
        print(
            "AVISO: ADMIN_CREDENCIAL, ADMIN_NOME e ADMIN_SENHA não definidos — "
            "nenhum administrador foi criado."
        )
        return

    existente = conexao.execute(
        sa.text(
            "SELECT id, senha_hash FROM docentes WHERE credencial_institucional = :c"
        ),
        {"c": credencial},
    ).first()
    if existente is not None:
        if not verificar_senha(senha, existente.senha_hash):
            raise ValueError(
                "ADMIN_CREDENCIAL já pertence a uma conta cuja senha não é a "
                "ADMIN_SENHA; escolha outra credencial ou use a senha da conta."
            )
        conexao.execute(
            sa.text("UPDATE docentes SET perfil = 'ADMINISTRADOR' WHERE id = :i"),
            {"i": existente.id},
        )
        return

    try:
        dados = DocenteCriar(
            nome=nome, credencial_institucional=credencial, senha=senha
        )
    except ValidationError as exc:
        raise ValueError(
            f"ADMIN_SENHA, ADMIN_NOME ou ADMIN_CREDENCIAL inválidos: {exc}"
        ) from None
    conexao.execute(
        sa.text(
            "INSERT INTO docentes (nome, credencial_institucional, senha_hash, perfil) "
            "VALUES (:n, :c, :h, 'ADMINISTRADOR')"
        ),
        {"n": dados.nome, "c": dados.credencial_institucional, "h": hash_senha(senha)},
    )


def _semear_prompt(conexao: sa.Connection) -> None:
    if conexao.execute(sa.text("SELECT 1 FROM prompts_mestres WHERE ativo")).first():
        return
    # A sessão entra na transação da migração: o commit dos services vira
    # savepoint, e quem confirma é o Alembic.
    with Session(bind=conexao) as db:
        inicial = db.scalar(
            sa.select(PromptMestre).where(PromptMestre.versao == VERSAO_INICIAL)
        )
        if inicial is None:
            registrar_versao(db, VERSAO_INICIAL, PAPEL_INICIAL, PARAMETROS_MARCADORES)
        ativar(db, VERSAO_INICIAL)


def upgrade() -> None:
    conexao = op.get_bind()
    _semear_admin(conexao)
    _semear_prompt(conexao)


def downgrade() -> None:
    # No-op declarado: ver docstring.
    pass
