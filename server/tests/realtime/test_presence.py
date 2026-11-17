"""Tests for presence: the room list and room details say who has Blender connected."""

import pytest

from tests.accounts import bearer, ensure_room, join, token_for
from tests.catchup import read_catch_up

ROOM = "studio"


@pytest.fixture
def bob(client):
    """bob's headers: an editor in "studio", which tester (the client's own user) hosts."""
    ensure_room(client, ROOM)
    headers = bearer(token_for(client, "bob"))
    join(client, ROOM, headers)
    return headers


def _connect(client, headers=None):
    return client.websocket_connect(f"/ws/rooms/{ROOM}", headers=headers or {})


def _presence(client, headers=None):
    listed = client.get("/api/rooms", headers=headers or {}).json()[0]["online"]
    detail = client.get(f"/api/rooms/{ROOM}", headers=headers or {}).json()["online"]
    assert listed == detail
    return listed


def test_an_empty_room_has_nobody(client, bob):
    assert _presence(client) == []


def test_connects_and_disconnects_show_up_for_every_member(client, bob):
    with _connect(client) as owner:
        read_catch_up(owner)
        with _connect(client, bob) as editor:
            read_catch_up(editor)
            assert _presence(client) == _presence(client, bob) == [
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


def test_a_refused_socket_never_counts(client, bob):
    outsider = bearer(token_for(client, "mallory"))
    with _connect(client, outsider):
        pass
    assert _presence(client) == []
