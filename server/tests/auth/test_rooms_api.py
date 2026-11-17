"""Tests for the rooms REST API: host, join by name and password, list, roles, members, delete."""

import pytest
from sqlalchemy import func, select

from app.db.models import Operation, Room, RoomMember
from tests.accounts import ROOM_PASSWORD, bearer, join, token_for
from tests.catchup import read_catch_up


@pytest.fixture
def users(anon):
    """Tokens for alice, bob and carol, as request headers."""
    return {name: bearer(token_for(anon, name)) for name in ("alice", "bob", "carol")}


def _host(anon, headers, room_id="studio", password=ROOM_PASSWORD):
    return anon.post("/api/rooms", json={"room_id": room_id, "password": password}, headers=headers)


@pytest.fixture
def room(anon, users):
    """Room "studio", hosted by alice."""
    assert _host(anon, users["alice"]).status_code == 201
    return "studio"


def _join(anon, headers, room_id="studio", password=ROOM_PASSWORD):
    return anon.post("/api/rooms/join", json={"room_id": room_id, "password": password}, headers=headers)


def _members(anon, headers, room="studio"):
    body = anon.get(f"/api/rooms/{room}", headers=headers).json()
    return {member["username"]: member["role"] for member in body["members"]}


def test_hosting_a_room_makes_you_its_owner(anon, users):
    created = _host(anon, users["alice"])

    assert created.status_code == 201
    assert created.json() == {
        "room_id": "studio",
        "role": "owner",
        "host": "alice",
        "created_at": created.json()["created_at"],
        "file": None,
        "online": [],
        "save_requests": [],
    }
    assert _members(anon, users["alice"]) == {"alice": "owner"}


def test_a_taken_room_name_is_409(anon, users, room):
    assert _host(anon, users["bob"]).status_code == 409


@pytest.mark.parametrize("room_id", ["", "has space", "x" * 65, "semi;colon"])
def test_a_bad_room_name_is_422(anon, users, room_id):
    assert _host(anon, users["alice"], room_id).status_code == 422


@pytest.mark.parametrize("password", ["", "abc", "x" * 257])
def test_a_room_needs_a_password_of_a_sensible_length(anon, users, password):
    assert _host(anon, users["alice"], password=password).status_code == 422


def test_the_password_is_stored_hashed(anon, users, room):
    async def _stored():
        async with anon.app.state.sessions() as session:
            return await session.scalar(select(Room.password_hash))

    stored = anon.portal.call(_stored)
    assert stored.startswith("scrypt$") and ROOM_PASSWORD not in stored


def test_name_and_password_join_as_an_editor(anon, users, room):
    joined = _join(anon, users["bob"])

    assert joined.status_code == 200
    assert (joined.json()["role"], joined.json()["host"]) == ("editor", "alice")
    assert _members(anon, users["alice"]) == {"alice": "owner", "bob": "editor"}


def test_a_wrong_password_and_a_missing_room_get_the_same_refusal(anon, users, room):
    wrong = _join(anon, users["bob"], password="not it")
    missing = _join(anon, users["bob"], room_id="nowhere")
    odd = _join(anon, users["bob"], room_id="not a room name!")

    assert wrong.status_code == missing.status_code == odd.status_code == 403
    assert wrong.json() == missing.json() == odd.json() == {"detail": "wrong room name or password"}
    assert _members(anon, users["alice"]) == {"alice": "owner"}


def test_joining_again_keeps_the_role_you_have(anon, users, room):
    _join(anon, users["bob"])
    anon.patch(f"/api/rooms/{room}/members/bob", json={"role": "viewer"}, headers=users["alice"])

    assert _join(anon, users["bob"]).json()["role"] == "viewer"
    assert _join(anon, users["alice"]).json()["role"] == "owner"


def test_repeated_wrong_passwords_are_cut_off(anon, users, room):
    for _ in range(10):
        assert _join(anon, users["bob"], password="guess").status_code == 403

    blocked = _join(anon, users["bob"])  # even the right one, until the window passes

    assert blocked.status_code == 429 and "Retry-After" in blocked.headers


def test_my_rooms_lists_only_mine_with_my_role(anon, users, room):
    _host(anon, users["bob"], "bobs")
    join(anon, room, users["bob"], "viewer", owner=users["alice"])

    alice = anon.get("/api/rooms", headers=users["alice"]).json()
    bob = anon.get("/api/rooms", headers=users["bob"]).json()
    carol = anon.get("/api/rooms", headers=users["carol"]).json()

    assert [(r["room_id"], r["role"], r["host"]) for r in alice] == [("studio", "owner", "alice")]
    assert [(r["room_id"], r["role"], r["host"]) for r in bob] == [
        ("bobs", "owner", "bob"),
        ("studio", "viewer", "alice"),
    ]
    assert carol == []


def test_room_details_are_for_members_only(anon, users, room):
    assert anon.get(f"/api/rooms/{room}", headers=users["bob"]).status_code == 403
    assert anon.get("/api/rooms/nowhere", headers=users["bob"]).status_code == 404


def test_an_owner_changes_roles(anon, users, room):
    _join(anon, users["bob"])

    changed = anon.patch(f"/api/rooms/{room}/members/bob", json={"role": "viewer"}, headers=users["alice"])

    assert changed.json()["role"] == "viewer"
    assert _members(anon, users["alice"])["bob"] == "viewer"


def test_a_non_owner_cant_change_roles(anon, users, room):
    _join(anon, users["bob"])

    response = anon.patch(f"/api/rooms/{room}/members/bob", json={"role": "owner"}, headers=users["bob"])

    assert response.status_code == 403


def test_the_last_owner_cant_step_down_or_leave(anon, users, room):
    demote = anon.patch(f"/api/rooms/{room}/members/alice", json={"role": "editor"}, headers=users["alice"])
    leave = anon.delete(f"/api/rooms/{room}/members/alice", headers=users["alice"])

    assert demote.status_code == leave.status_code == 409
    assert _members(anon, users["alice"]) == {"alice": "owner"}


def test_with_a_second_owner_the_first_can_leave(anon, users, room):
    _join(anon, users["bob"])
    anon.patch(f"/api/rooms/{room}/members/bob", json={"role": "owner"}, headers=users["alice"])

    assert anon.delete(f"/api/rooms/{room}/members/alice", headers=users["alice"]).status_code == 204
    assert _members(anon, users["bob"]) == {"bob": "owner"}


def test_an_owner_removes_a_member(anon, users, room):
    _join(anon, users["bob"])

    assert anon.delete(f"/api/rooms/{room}/members/bob", headers=users["alice"]).status_code == 204

    assert _members(anon, users["alice"]) == {"alice": "owner"}
    assert anon.get(f"/api/rooms/{room}", headers=users["bob"]).status_code == 403


def test_a_member_can_leave_but_not_remove_others(anon, users, room):
    _join(anon, users["bob"])
    _join(anon, users["carol"])

    assert anon.delete(f"/api/rooms/{room}/members/carol", headers=users["bob"]).status_code == 403
    assert anon.delete(f"/api/rooms/{room}/members/bob", headers=users["bob"]).status_code == 204
    assert _members(anon, users["alice"]) == {"alice": "owner", "carol": "editor"}


def test_changing_someone_not_in_the_room_is_404(anon, users, room):
    path = f"/api/rooms/{room}/members"
    assert anon.patch(f"{path}/carol", json={"role": "viewer"}, headers=users["alice"]).status_code == 404
    assert anon.delete(f"{path}/nobody", headers=users["alice"]).status_code == 404


def test_only_the_owner_deletes_a_room(anon, users, room):
    _join(anon, users["bob"])
    assert anon.delete(f"/api/rooms/{room}", headers=users["bob"]).status_code == 403
    assert anon.delete(f"/api/rooms/{room}", headers=users["carol"]).status_code == 403


def test_deleting_a_room_removes_its_members_and_history_and_frees_the_name(anon, users, room):
    _join(anon, users["bob"])
    op = {
        "kind": "set",
        "object": "6c1f2a9e-3b4d-4e5f-8a7b-9c0d1e2f3a4b",
        "property": "location",
        "value": [1.0, 2.0, 3.0],
        "lamport": 1,
        "origin": "0b7e5d21-8f3c-4a6b-9d2e-1f4a5b6c7d8e",
    }
    with anon.websocket_connect(f"/ws/rooms/{room}", headers=users["alice"]) as ws:
        read_catch_up(ws)
        ws.send_json({"v": 1, "type": "ops", "ops": [op]})
        ws.send_text("not json")
        ws.receive_text()  # the error for the line above, so the op before it is saved by now
        deleted = anon.delete(f"/api/rooms/{room}", headers=users["alice"])

    async def _left():
        async with anon.app.state.sessions() as session:
            return [
                await session.scalar(select(func.count()).select_from(model))
                for model in (Operation, RoomMember, Room)
            ]

    assert deleted.status_code == 204
    assert anon.portal.call(_left) == [0, 0, 0]
    assert anon.get("/api/rooms", headers=users["bob"]).json() == []
    assert _host(anon, users["bob"]).status_code == 201
    with anon.websocket_connect(f"/ws/rooms/{room}", headers=users["bob"]) as ws:
        assert read_catch_up(ws) == ([], 0)  # the new room doesn't inherit the old one's log


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/rooms"),
        ("GET", "/api/rooms"),
        ("POST", "/api/rooms/join"),
        ("GET", "/api/rooms/studio"),
        ("DELETE", "/api/rooms/studio"),
        ("PUT", "/api/rooms/studio/file"),
        ("GET", "/api/rooms/studio/file"),
        ("PATCH", "/api/rooms/studio/members/bob"),
        ("DELETE", "/api/rooms/studio/members/bob"),
        ("POST", "/api/rooms/studio/save-requests/abc"),
    ],
)
def test_every_rooms_route_needs_a_token(anon, room, method, path):
    assert anon.request(method, path).status_code == 401
