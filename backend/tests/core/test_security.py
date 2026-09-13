import time

import jwt
import pytest

from backend.app.core.security import (
    criar_access_token,
    decodificar_token,
    hash_senha,
    verificar_senha,
)
from backend.app.exceptions import TokenInvalidoException


def test_hash_senha_nao_retorna_texto_puro():
    assert hash_senha("minhasenha123") != "minhasenha123"


def test_verificar_senha_aceita_senha_correta():
    hash_ = hash_senha("minhasenha123")
    assert verificar_senha("minhasenha123", hash_) is True


def test_verificar_senha_rejeita_senha_errada():
    hash_ = hash_senha("minhasenha123")
    assert verificar_senha("outrasenha", hash_) is False


def test_criar_e_decodificar_token_roundtrip():
    token = criar_access_token(subject="42")
    payload = decodificar_token(token)
    assert payload["sub"] == "42"


def test_decodificar_token_invalido_levanta_excecao_de_dominio():
    with pytest.raises(TokenInvalidoException):
        decodificar_token("token.invalido.aqui")


def test_decodificar_token_expirado_levanta_excecao_de_dominio(monkeypatch):
    import backend.app.core.security as security_module

    monkeypatch.setattr(security_module.settings, "access_token_expire_minutes", -1)
    token = criar_access_token(subject="42")
    with pytest.raises(TokenInvalidoException):
        decodificar_token(token)
