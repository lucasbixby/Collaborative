"""Tests for GET /api/rooms/{room_id}/presence (#22): who has a socket open in a room."""

import pytest

from tests.accounts import bearer, ensure_room, token_for
from tests.catchup import read_catch_up

ROOM = "studio"


@pytest.fixture
def bob(client):
    """bob's headers: an editor in "studio", which tester (the client's own user) owns."""
    ensure_room(client, ROOM)
    headers = bearer(token_for(client, "bob"))
    code = client.post(f"/api/rooms/{ROOM}/invites", json={"role": "editor"}).json()["code"]
    assert client.post(f"/api/rooms/join/{code}", headers=headers).status_code == 200
    return headers


def _connect(client, headers=None):
    return client.websocket_connect(f"/ws/rooms/{ROOM}", headers=headers or {})


def _presence(client, headers=None):
    response = client.get(f"/api/rooms/{ROOM}/presence", headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()["users"]


def test_an_empty_room_has_nobody(client, bob):
    assert _presence(client) == []


def test_connects_and_disconnects_show_up(client, bob):
    with _connect(client) as owner:
        read_catch_up(owner)
        with _connect(client, bob) as editor:
            read_catch_up(editor)
            assert _presence(client) == [
                {"username": "bob", "role": "editor", "connections": 1},
                {"username": "tester", "role": "owner", "connections": 1},
            ]
        assert _presence(client) == [{"username": "tester", "role": "owner", "connections": 1}]
    assert _presence(client) == []


def test_two_blenders_for_one_user_count_twice(client, bob):
    with _connect(client, bob) as first, _connect(client, bob) as second:
        read_catch_up(first)
        read_catch_up(second)
        assert _presence(client) == [{"username": "bob", "role": "editor", "connections": 2}]


def test_a_role_change_shows_at_once(client, bob):
    with _connect(client, bob) as editor:
        read_catch_up(editor)
        client.patch(f"/api/rooms/{ROOM}/members/bob", json={"role": "viewer"})
        assert _presence(client) == [{"username": "bob", "role": "viewer", "connections": 1}]


def test_presence_is_for_members_only(client, bob):
    outsider = bearer(token_for(client, "mallory"))
    assert client.get(f"/api/rooms/{ROOM}/presence", headers=outsider).status_code == 403
    assert client.get("/api/rooms/nowhere/presence").status_code == 404
    assert client.get(f"/api/rooms/{ROOM}/presence", headers={"Authorization": ""}).status_code == 401


def test_a_refused_socket_never_counts(client, bob):
    outsider = bearer(token_for(client, "mallory"))
    with _connect(client, outsider):
        pass
    assert _presence(client) == []
