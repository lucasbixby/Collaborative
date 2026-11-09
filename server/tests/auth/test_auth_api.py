"""Tests for register / login / me (#16), and that the REST API needs a token."""

import pytest
from sqlalchemy import select

from app.db.models import User
from tests.accounts import PASSWORD, bearer, token_for


def _register(anon, username, password=PASSWORD):
    return anon.post("/api/auth/register", json={"username": username, "password": password})


def _login(anon, username, password=PASSWORD):
    return anon.post("/api/auth/login", json={"username": username, "password": password})


def test_register_then_login_then_me(anon):
    created = _register(anon, "alice")
    assert created.status_code == 201
    assert created.json()["username"] == "alice"
    assert "password" not in created.text

    login = _login(anon, "alice")
    assert login.status_code == 200
    assert login.json()["user"] == created.json()

    me = anon.get("/api/auth/me", headers=bearer(login.json()["token"]))
    assert me.status_code == 200
    assert me.json() == created.json()


def test_usernames_are_lowercased(anon):
    assert _register(anon, "Alice").json()["username"] == "alice"
    assert _login(anon, "ALICE").status_code == 200
    assert _register(anon, "alice").status_code == 409


def test_a_duplicate_username_is_409(anon):
    assert _register(anon, "alice").status_code == 201
    assert _register(anon, "alice", "another password").status_code == 409


@pytest.mark.parametrize("username", ["ab", "x" * 33, "has space", "semi;colon", "é-accent", ""])
def test_a_bad_username_is_refused(anon, username):
    assert _register(anon, username).status_code == 422


def test_a_short_password_is_refused(anon):
    assert _register(anon, "alice", "seven77").status_code == 422
    assert _register(anon, "alice", "eight888").status_code == 201


def test_wrong_password_and_unknown_user_get_the_same_error(anon):
    _register(anon, "alice")
    wrong_password = _login(anon, "alice", "not the password")
    unknown_user = _login(anon, "nobody")
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json() == {"detail": "wrong username or password"}


def test_the_password_is_stored_hashed(anon):
    _register(anon, "alice")

    async def _stored():
        async with anon.app.state.sessions() as session:
            return await session.scalar(select(User.password_hash))

    stored = anon.portal.call(_stored)
    assert PASSWORD not in stored
    assert stored.startswith("scrypt$")


def test_a_token_for_a_deleted_user_is_refused(anon):
    token = token_for(anon, "alice")

    async def _delete():
        async with anon.app.state.sessions() as session:
            await session.delete(await session.scalar(select(User)))
            await session.commit()

    anon.portal.call(_delete)
    assert anon.get("/api/auth/me", headers=bearer(token)).status_code == 401


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer not-a-token"}, {"Authorization": "Basic YWxpY2U6cHc="}],
)
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/auth/me"),
        ("GET", "/api/rooms/demo/snapshot"),
        ("GET", "/api/rooms/demo/operations"),
    ],
)
def test_protected_routes_need_a_valid_token(anon, method, path, headers):
    response = anon.request(method, path, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_health_register_and_login_need_no_token(anon):
    assert anon.get("/health").status_code == 200
    assert _register(anon, "alice").status_code == 201
    assert _login(anon, "alice").status_code == 200
