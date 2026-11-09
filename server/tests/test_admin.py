"""Tests for scripts/admin.py (#16-#18), run as a real process against the test's database."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.accounts import PASSWORD, bearer

ADMIN = Path(__file__).resolve().parents[1] / "scripts" / "admin.py"


@pytest.fixture
def admin(database_url):
    def run(*args, check=True) -> subprocess.CompletedProcess:
        env = {**os.environ, "COLLAB_DATABASE_URL": database_url, "COLLAB_PASSWORD": PASSWORD}
        result = subprocess.run(
            [sys.executable, str(ADMIN), *args],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if check:
            assert result.returncode == 0, result.stderr
        return result

    return run


def test_create_user_then_sign_in_with_the_password(admin, database_url):
    assert "created user 'alice'" in admin("create-user", "Alice").stdout
    with TestClient(create_app(database_url)) as test_client:
        response = test_client.post(
            "/api/auth/login", json={"username": "alice", "password": PASSWORD}
        )
    assert response.status_code == 200


def test_token_prints_a_token_the_server_accepts(admin, database_url):
    admin("create-user", "alice")
    token = admin("token", "alice").stdout.strip()
    with TestClient(create_app(database_url)) as test_client:
        me = test_client.get("/api/auth/me", headers=bearer(token))
    assert me.json()["username"] == "alice"


def test_errors_are_one_line_and_exit_1(admin):
    admin("create-user", "alice")
    again = admin("create-user", "alice", check=False)
    assert (again.returncode, again.stderr) == (1, "error: user 'alice' already exists\n")
    missing = admin("token", "nobody", check=False)
    assert (missing.returncode, missing.stderr) == (1, "error: no user 'nobody'\n")
    short = admin("create-user", "bob", "--password", "short", check=False)
    assert short.returncode == 1 and "at least 8" in short.stderr
    bad_name = admin("create-user", "no spaces", check=False)
    assert bad_name.returncode == 1 and "3-32" in bad_name.stderr


def test_create_room_and_add_member_give_those_roles(admin, database_url):
    for name in ("alice", "bob"):
        admin("create-user", name)
    assert "owned by 'alice'" in admin("create-room", "studio", "--owner", "alice").stdout
    assert "'bob' is now viewer" in admin("add-member", "studio", "bob", "--role", "viewer").stdout
    bob = admin("token", "bob").stdout.strip()

    with TestClient(create_app(database_url)) as test_client:
        rooms = test_client.get("/api/rooms", headers=bearer(bob)).json()
    assert [(room["room_id"], room["role"]) for room in rooms] == [("studio", "viewer")]


def test_room_errors(admin):
    admin("create-user", "alice")
    admin("create-room", "studio", "--owner", "alice")
    taken = admin("create-room", "studio", "--owner", "alice", check=False)
    assert taken.stderr == "error: room 'studio' already exists\n"
    no_room = admin("add-member", "nowhere", "alice", check=False)
    assert no_room.stderr == "error: no room 'nowhere'\n"
    bad_id = admin("create-room", "has space", "--owner", "alice", check=False)
    assert bad_id.returncode == 1 and "1-64" in bad_id.stderr
