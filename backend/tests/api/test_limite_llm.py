"""Achado 6: rota de LLM segura uma thread do pool (~40) por minutos. Sem teto,
poucas gerações simultâneas — ou um cliente repetindo após timeout — param a API
inteira, /auth/login e /health inclusos. O teto responde 503 na hora."""

import threading

import pytest

from backend.app.api import deps
from backend.app.exceptions import ServidorOcupadoException


@pytest.fixture
def uma_vaga(monkeypatch):
    monkeypatch.setattr(deps, "_vagas_llm", threading.BoundedSemaphore(1))
    monkeypatch.setattr(deps, "criar_provedor_service", lambda db: object())


def test_sem_vaga_livre_responde_503_com_retry_after(uma_vaga):
    primeira = deps.get_provedor(db=None)
    next(primeira)  # ocupa a única vaga

    with pytest.raises(ServidorOcupadoException) as erro:
        next(deps.get_provedor(db=None))

    assert erro.value.status_code == 503
    assert "Retry-After" in erro.value.headers
    primeira.close()


def test_a_vaga_e_devolvida_ao_terminar_a_requisicao(uma_vaga):
    primeira = deps.get_provedor(db=None)
    next(primeira)
    primeira.close()  # fim da requisição

    segunda = deps.get_provedor(db=None)
    assert next(segunda) is not None
    segunda.close()


def test_a_vaga_e_devolvida_mesmo_quando_a_requisicao_falha(uma_vaga):
    primeira = deps.get_provedor(db=None)
    next(primeira)
    with pytest.raises(RuntimeError):
        primeira.throw(RuntimeError("falha no endpoint"))

    segunda = deps.get_provedor(db=None)
    assert next(segunda) is not None
    segunda.close()


def test_sob_demanda_nao_toma_vaga_sem_chamada(uma_vaga):
    ocioso = deps.get_provedor_sob_demanda(db=None)
    next(ocioso)  # ramo determinístico: nunca chama `obter`
    next(deps.get_provedor(db=None))  # a vaga ainda está livre

    ocioso.close()


def test_sob_demanda_toma_vaga_na_chamada_e_devolve(uma_vaga):
    gen = deps.get_provedor_sob_demanda(db=None)
    obter = next(gen)
    obter()
    with pytest.raises(ServidorOcupadoException):
        next(deps.get_provedor(db=None))

    gen.close()
    next(deps.get_provedor(db=None))  # devolvida ao fim da requisição
