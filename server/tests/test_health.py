from fastapi.testclient import TestClient

from app.config import DEFAULT_SECRET_KEY, settings
from app.main import create_app


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_warns_about_the_default_secret_key(database_url, monkeypatch, caplog):
    monkeypatch.setattr(settings, "secret_key", DEFAULT_SECRET_KEY)
    with TestClient(create_app(database_url)):
        pass
    assert "COLLAB_SECRET_KEY" in caplog.text


def test_the_default_key_warning_says_it_signs_tokens(database_url, monkeypatch, caplog):
    monkeypatch.setattr(settings, "secret_key", DEFAULT_SECRET_KEY)
    with TestClient(create_app(database_url)):
        pass
    assert "sign in as any user" in caplog.text


def test_startup_warns_about_a_short_secret_key(database_url, monkeypatch, caplog):
    monkeypatch.setattr(settings, "secret_key", "something-else")
    with TestClient(create_app(database_url)):
        pass
    assert "under 32 bytes" in caplog.text
    assert "sign in as any user" not in caplog.text


def test_startup_is_quiet_about_a_long_custom_secret_key(database_url, monkeypatch, caplog):
    monkeypatch.setattr(settings, "secret_key", "x" * 32)
    with TestClient(create_app(database_url)):
        pass
    assert "COLLAB_SECRET_KEY" not in caplog.text
