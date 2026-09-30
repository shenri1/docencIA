import json
from datetime import UTC, datetime, timedelta

import jwt

from backend.app.core.config import settings
from backend.app.core.security import criar_access_token
from backend.app.domain import PerfilDocente, TipoEventoAuditoria
from backend.app.models.auditoria import RegistroAuditoria
from backend.app.models.identidade import Docente
from backend.app.services.log_auditoria import pseudonimo, pseudonimo_credencial
from backend.tests.conftest import _auth

E = TipoEventoAuditoria


def eventos(db, tipo):
    return db.query(RegistroAuditoria).filter_by(tipo_evento=tipo.value).all()


def docente_de(db, credencial) -> Docente:
    return db.query(Docente).filter_by(credencial_institucional=credencial).one()


def login(client, usuario, senha):
    return client.post("/auth/login", data={"username": usuario, "password": senha})


def test_login_com_senha_errada(client, db_session):
    _auth(client, "seg-senha")
    resposta = login(client, "seg-senha", "senha-errada-123")

    assert resposta.status_code == 401
    [evento] = eventos(db_session, E.LOGIN_FALHO)
    docente = docente_de(db_session, "seg-senha")
    assert evento.ator == pseudonimo(docente.id)
    assert evento.entidade_afetada == f"docentes:{docente.id}"
    assert evento.payload == {"motivo": "senha_incorreta"}


def test_login_com_credencial_inexistente(client, db_session):
    resposta = login(client, "ninguem-aqui", "qualquer-123")

    assert resposta.status_code == 401
    [evento] = eventos(db_session, E.LOGIN_FALHO)
    assert evento.ator is None
    assert evento.entidade_afetada == "docentes"
    assert evento.payload == {
        "motivo": "credencial_inexistente",
        "credencial_pseudonimo": pseudonimo_credencial("ninguem-aqui"),
    }


def test_resposta_de_login_falho_e_identica_nos_dois_casos(client, db_session):
    _auth(client, "seg-igual")
    errada = login(client, "seg-igual", "senha-errada-123")
    inexistente = login(client, "seg-nao-existe", "senha-errada-123")
    assert errada.status_code == inexistente.status_code == 401
    assert errada.json() == inexistente.json()


def test_senha_no_campo_de_usuario_nao_vai_para_o_log(client, db_session):
    login(client, "MinhaSenhaSecreta!2026", "x")
    for registro in db_session.query(RegistroAuditoria).all():
        assert "MinhaSenhaSecreta" not in (registro.ator or "")
        assert "MinhaSenhaSecreta" not in json.dumps(registro.payload)


def _me(client, token):
    return client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})


def test_tokens_suspeitos_viram_evento_e_expirado_nao(client, db_session):
    headers = _auth(client, "seg-token")
    docente = docente_de(db_session, "seg-token")
    valido = headers["Authorization"].removeprefix("Bearer ")
    agora = datetime.now(UTC)

    outra_chave = jwt.encode(
        {"sub": str(docente.id), "exp": agora + timedelta(minutes=5)},
        "outra-chave-qualquer-com-32-bytes!!",
        algorithm=settings.algorithm,
    )
    truncado = valido[:-5]
    sub_texto = criar_access_token(subject="abc")
    apagado = criar_access_token(subject="999999")
    expirado = jwt.encode(
        {"sub": str(docente.id), "exp": agora - timedelta(minutes=1)},
        settings.secret_key,
        algorithm=settings.algorithm,
    )

    corpos = [_me(client, t) for t in (outra_chave, truncado, sub_texto, apagado, expirado)]
    assert {r.status_code for r in corpos} == {401}
    # O cliente nunca aprende o motivo.
    assert len({json.dumps(r.json(), sort_keys=True) for r in corpos}) == 1

    motivos = sorted(e.payload["motivo"] for e in eventos(db_session, E.TOKEN_SUSPEITO))
    assert motivos == [
        "assinatura_invalida",
        "assinatura_invalida",
        "docente_inexistente",
        "sub_invalido",
    ]
    [inexistente] = [
        e for e in eventos(db_session, E.TOKEN_SUSPEITO)
        if e.payload["motivo"] == "docente_inexistente"
    ]
    assert inexistente.ator == pseudonimo(999999)


def test_requisicao_sem_token_nao_e_evento(client, db_session):
    assert client.get("/auth/me").status_code == 401
    assert eventos(db_session, E.TOKEN_SUSPEITO) == []


def test_docente_em_rota_de_admin_grava_acesso_negado(client, db_session):
    headers = _auth(client, "seg-perfil")
    resposta = client.get("/prompts", headers=headers)

    assert resposta.status_code == 403
    [evento] = eventos(db_session, E.ACESSO_NEGADO)
    docente = docente_de(db_session, "seg-perfil")
    assert evento.ator == pseudonimo(docente.id)
    assert evento.payload == {"perfil": "docente", "perfil_exigido": "administrador"}


def test_admin_nao_grava_acesso_negado(client, db_session):
    headers = _auth(client, "seg-admin")
    docente = docente_de(db_session, "seg-admin")
    docente.perfil = PerfilDocente.ADMINISTRADOR
    db_session.commit()
    assert client.get("/prompts", headers=headers).status_code == 200
    assert eventos(db_session, E.ACESSO_NEGADO) == []
