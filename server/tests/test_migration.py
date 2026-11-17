"""An older database gains the columns added to `rooms` since it was made."""

import sqlite3

from fastapi.testclient import TestClient

from app.main import create_app
from tests.accounts import bearer, token_for

OLD_ROOMS = """
CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username VARCHAR(32) UNIQUE,
                    password_hash VARCHAR(255), created_at DATETIME);
CREATE TABLE rooms (id VARCHAR(64) PRIMARY KEY, created_by INTEGER REFERENCES users(id),
                    created_at DATETIME);
"""


def test_a_database_from_before_room_passwords_still_starts(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as old:
        old.executescript(OLD_ROOMS)

    with TestClient(create_app(f"sqlite+aiosqlite:///{path}")) as client:
        alice = bearer(token_for(client, "alice"))
        created = client.post(
            "/api/rooms", json={"room_id": "studio", "password": "open sesame"}, headers=alice
        )
        assert created.status_code == 201
        assert client.get("/api/rooms", headers=alice).json()[0]["file"] is None
