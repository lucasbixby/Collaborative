from fastapi.testclient import TestClient

from app.auth import tokens
from app.config import KNOWN_WEAK_KEY, settings
from app.main import create_app


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_warns_about_the_old_placeholder_key(database_url, monkeypatch, caplog):
    monkeypatch.setattr(settings, "secret_key", KNOWN_WEAK_KEY)
    with TestClient(create_app(database_url)):
        pass
    assert "COLLAB_SECRET_KEY" in caplog.text


def test_the_placeholder_key_warning_says_what_it_allows(database_url, monkeypatch, caplog):
    monkeypatch.setattr(settings, "secret_key", KNOWN_WEAK_KEY)
    with TestClient(create_app(database_url)):
        pass
    assert "anyone can sign in" in caplog.text


def test_startup_warns_about_a_short_secret_key(database_url, monkeypatch, caplog):
    monkeypatch.setattr(settings, "secret_key", "something-else")
    with TestClient(create_app(database_url)):
        pass
    assert "under 32 bytes" in caplog.text
    assert "anyone can sign in" not in caplog.text


def test_startup_is_quiet_about_a_long_custom_secret_key(database_url, monkeypatch, caplog):
    monkeypatch.setattr(settings, "secret_key", "x" * 32)
    with TestClient(create_app(database_url)):
        pass
    assert "COLLAB_SECRET_KEY" not in caplog.text


def test_without_a_key_one_is_generated_and_kept(database_url, monkeypatch, tmp_path, caplog):
    key_file = tmp_path / "data" / "secret.key"
    monkeypatch.setattr(settings, "secret_key", "")
    monkeypatch.setattr(settings, "secret_key_file", key_file)
    with TestClient(create_app(database_url)):
        first = tokens.signing_key()
    monkeypatch.setattr(tokens, "_generated", {})  # as a restarted process would be
    with TestClient(create_app(database_url)):
        assert tokens.signing_key() == first

    assert len(first) >= 32 and key_file.read_text() == first
    assert key_file.stat().st_mode & 0o777 == 0o600
    assert "COLLAB_SECRET_KEY" not in caplog.text
