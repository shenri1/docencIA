from backend.app.core.config import Settings


def test_settings_tem_campos_de_autenticacao():
    settings = Settings()
    assert isinstance(settings.secret_key, str) and settings.secret_key
    assert settings.algorithm == "HS256"
    assert settings.access_token_expire_minutes == 480
