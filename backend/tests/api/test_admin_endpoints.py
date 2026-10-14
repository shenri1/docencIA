from datetime import UTC, datetime, timedelta

from backend.app.domain import PerfilDocente, TipoEventoAuditoria
from backend.app.models.identidade import Docente
from backend.app.services.log_auditoria import registrar_evento
from backend.tests.conftest import _auth


def admin(client, db_session, credencial="adm-logs"):
    headers = _auth(client, credencial)
    docente = (
        db_session.query(Docente).filter_by(credencial_institucional=credencial).one()
    )
    docente.perfil = PerfilDocente.ADMINISTRADOR
    db_session.commit()
    return headers, docente


def semear(db_session, docente_id):
    for tipo in (
        TipoEventoAuditoria.EXCLUSAO,
        TipoEventoAuditoria.CONGELAMENTO,
        TipoEventoAuditoria.EXCLUSAO,
    ):
        registrar_evento(db_session, tipo, "bancos_questoes:1", docente_id, {"n": 1})
    db_session.commit()


def test_logs_sem_token_e_401(client):
    assert client.get("/admin/logs").status_code == 401


def test_logs_para_docente_e_coordenador_e_403(client, db_session):
    headers = _auth(client, "adm-docente")
    assert client.get("/admin/logs", headers=headers).status_code == 403
    coordenador = (
        db_session.query(Docente)
        .filter_by(credencial_institucional="adm-docente")
        .one()
    )
    coordenador.perfil = PerfilDocente.COORDENADOR
    db_session.commit()
    assert client.get("/admin/logs", headers=headers).status_code == 403


def test_logs_filtra_por_tipo_e_ordena_do_mais_novo(client, db_session):
    headers, docente = admin(client, db_session)
    semear(db_session, docente.id)
    corpo = client.get(
        "/admin/logs", headers=headers, params={"tipo_evento": "exclusao"}
    ).json()
    assert [r["tipo_evento"] for r in corpo] == ["exclusao", "exclusao"]
    assert corpo[0]["id"] > corpo[1]["id"]
    assert set(corpo[0]) == {
        "id",
        "tipo_evento",
        "entidade_afetada",
        "ator",
        "payload",
        "timestamp",
    }


def test_logs_filtra_por_intervalo(client, db_session):
    headers, docente = admin(client, db_session, "adm-intervalo")
    semear(db_session, docente.id)
    futuro = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    assert (
        client.get("/admin/logs", headers=headers, params={"desde": futuro}).json()
        == []
    )
    todos = client.get("/admin/logs", headers=headers, params={"ate": futuro}).json()
    assert len([r for r in todos if r["entidade_afetada"] == "bancos_questoes:1"]) == 3


def test_logs_pagina(client, db_session):
    headers, docente = admin(client, db_session, "adm-pagina")
    semear(db_session, docente.id)
    params = {"tipo_evento": "exclusao"}
    primeira = client.get(
        "/admin/logs", headers=headers, params={**params, "limite": 1}
    ).json()
    segunda = client.get(
        "/admin/logs",
        headers=headers,
        params={**params, "limite": 1, "deslocamento": 1},
    ).json()
    assert len(primeira) == len(segunda) == 1
    assert primeira[0]["id"] > segunda[0]["id"]


def test_limite_fora_da_faixa_e_422(client, db_session):
    headers, _ = admin(client, db_session, "adm-422")
    for limite in (0, 501):
        resposta = client.get("/admin/logs", headers=headers, params={"limite": limite})
        assert resposta.status_code == 422


def test_logs_nao_expoem_a_credencial(client, db_session):
    headers, docente = admin(client, db_session, "adm-credencial")
    semear(db_session, docente.id)
    texto = client.get("/admin/logs", headers=headers).text
    assert "adm-credencial" not in texto
