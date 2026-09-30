"""Autenticação de docentes — não orquestra LLM (núcleo determinístico
auxiliar, infraestrutura de identidade)."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.security import (
    criar_access_token,
    decodificar_token,
    hash_senha,
    verificar_senha,
)
from backend.app.domain import PerfilDocente, TipoEventoAuditoria
from backend.app.exceptions import (
    CredenciaisInvalidasException,
    CredencialJaCadastradaException,
    PerfilInsuficienteException,
    TokenInvalidoException,
)
from backend.app.models.identidade import Docente
from backend.app.schemas.identidade import DocenteCriar
from backend.app.services.log_auditoria import (
    pseudonimo_credencial,
    registrar_evento,
)

# Hash de referência usado quando a credencial não existe, pra que
# autenticar_docente sempre pague o custo de um bcrypt.checkpw: evita que o
# tempo de resposta vaze se a conta existe (timing oracle). Calculado uma
# única vez na importação do módulo, não a cada requisição.
_HASH_DUMMY = hash_senha("dummy-password-for-timing-safety")

ORDEM_PERFIL = {
    PerfilDocente.DOCENTE: 0,
    PerfilDocente.COORDENADOR: 1,
    PerfilDocente.ADMINISTRADOR: 2,
}


def _registrar_recusa(
    db: Session,
    tipo: TipoEventoAuditoria,
    entidade: str,
    docente_id: int | None,
    payload: dict,
) -> None:
    """Commit antes do raise: o rollback do erro apagaria o registro da
    recusa. A sessão do request não tem nada pendente aqui — autenticar é a
    primeira coisa que ele faz."""
    registrar_evento(db, tipo, entidade, docente_id, payload)
    db.commit()


def registrar_docente(db: Session, dados: DocenteCriar) -> Docente:
    existente = (
        db.query(Docente)
        .filter_by(credencial_institucional=dados.credencial_institucional)
        .first()
    )
    if existente is not None:
        raise CredencialJaCadastradaException(dados.credencial_institucional)

    docente = Docente(
        nome=dados.nome,
        credencial_institucional=dados.credencial_institucional,
        senha_hash=hash_senha(dados.senha),
        perfil=PerfilDocente.DOCENTE,
    )
    db.add(docente)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise CredencialJaCadastradaException(dados.credencial_institucional) from None
    db.refresh(docente)
    return docente


def autenticar_docente(db: Session, credencial_institucional: str, senha: str) -> str:
    docente = (
        db.query(Docente)
        .filter_by(credencial_institucional=credencial_institucional)
        .first()
    )
    senha_hash_referencia = docente.senha_hash if docente is not None else _HASH_DUMMY
    senha_confere = verificar_senha(senha, senha_hash_referencia)
    # Os dois ramos de falha fazem o mesmo trabalho (um INSERT e um commit):
    # o log não reabre o timing oracle que o _HASH_DUMMY fecha.
    if docente is None:
        # A credencial digitada nunca vai em claro: é dado pessoal, e às vezes
        # é a senha digitada no campo errado.
        _registrar_recusa(
            db,
            TipoEventoAuditoria.LOGIN_FALHO,
            "docentes",
            None,
            {
                "motivo": "credencial_inexistente",
                "credencial_pseudonimo": pseudonimo_credencial(
                    credencial_institucional
                ),
            },
        )
        raise CredenciaisInvalidasException()
    if not senha_confere:
        _registrar_recusa(
            db,
            TipoEventoAuditoria.LOGIN_FALHO,
            f"docentes:{docente.id}",
            docente.id,
            {"motivo": "senha_incorreta"},
        )
        raise CredenciaisInvalidasException()
    return criar_access_token(subject=str(docente.id))


def docente_do_token(db: Session, token: str) -> Docente:
    """Token expirado é fim normal de sessão e não vira evento; os demais
    motivos são suspeitos."""
    try:
        payload = decodificar_token(token)
    except TokenInvalidoException as exc:
        if exc.motivo != "expirado":
            _registrar_recusa(
                db,
                TipoEventoAuditoria.TOKEN_SUSPEITO,
                "docentes",
                None,
                {"motivo": exc.motivo},
            )
        raise
    try:
        docente_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        _registrar_recusa(
            db,
            TipoEventoAuditoria.TOKEN_SUSPEITO,
            "docentes",
            None,
            {"motivo": "sub_invalido"},
        )
        raise TokenInvalidoException(motivo="sub_invalido") from exc
    docente = db.get(Docente, docente_id)
    if docente is None:
        # Assinatura válida: o id é do sistema, de um docente que não existe
        # mais.
        _registrar_recusa(
            db,
            TipoEventoAuditoria.TOKEN_SUSPEITO,
            f"docentes:{docente_id}",
            docente_id,
            {"motivo": "docente_inexistente"},
        )
        raise TokenInvalidoException(motivo="docente_inexistente")
    return docente


def exigir_perfil(db: Session, docente: Docente, minimo: PerfilDocente) -> None:
    if ORDEM_PERFIL[docente.perfil] < ORDEM_PERFIL[minimo]:
        _registrar_recusa(
            db,
            TipoEventoAuditoria.ACESSO_NEGADO,
            f"docentes:{docente.id}",
            docente.id,
            {"perfil": docente.perfil.value, "perfil_exigido": minimo.value},
        )
        raise PerfilInsuficienteException()
