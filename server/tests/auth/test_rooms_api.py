"""Tests for the rooms REST API (#18): create, list, invites, join, roles, members."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.db.models import Invite
from tests.accounts import bearer, token_for


@pytest.fixture
def users(anon):
    """Tokens for alice, bob and carol, as request headers."""
    return {name: bearer(token_for(anon, name)) for name in ("alice", "bob", "carol")}


@pytest.fixture
def room(anon, users):
    """Room "studio", owned by alice."""
    assert anon.post("/api/rooms", json={"room_id": "studio"}, headers=users["alice"]).status_code == 201
    return "studio"


def _invite(anon, headers, role="editor", room="studio", **extra):
    return anon.post(f"/api/rooms/{room}/invites", json={"role": role, **extra}, headers=headers)


def _join(anon, headers, code):
    return anon.post(f"/api/rooms/join/{code}", headers=headers)


def _members(anon, headers, room="studio"):
    body = anon.get(f"/api/rooms/{room}", headers=headers).json()
    return {member["username"]: member["role"] for member in body["members"]}


def test_creating_a_room_makes_you_its_owner(anon, users):
    created = anon.post("/api/rooms", json={"room_id": "studio"}, headers=users["alice"])

    assert created.status_code == 201
    assert created.json()["role"] == "owner"
    assert _members(anon, users["alice"]) == {"alice": "owner"}


def test_a_taken_room_id_is_409(anon, users, room):
    response = anon.post("/api/rooms", json={"room_id": room}, headers=users["bob"])
    assert response.status_code == 409


@pytest.mark.parametrize("room_id", ["", "has space", "x" * 65, "semi;colon"])
def test_a_bad_room_id_is_422(anon, users, room_id):
    assert anon.post("/api/rooms", json={"room_id": room_id}, headers=users["alice"]).status_code == 422


def test_my_rooms_lists_only_mine_with_my_role(anon, users, room):
    anon.post("/api/rooms", json={"room_id": "bobs"}, headers=users["bob"])
    _join(anon, users["bob"], _invite(anon, users["alice"], "viewer").json()["code"])

    alice = anon.get("/api/rooms", headers=users["alice"]).json()
    bob = anon.get("/api/rooms", headers=users["bob"]).json()
    carol = anon.get("/api/rooms", headers=users["carol"]).json()

    assert [(r["room_id"], r["role"]) for r in alice] == [("studio", "owner")]
    assert [(r["room_id"], r["role"]) for r in bob] == [("bobs", "owner"), ("studio", "viewer")]
    assert carol == []


def test_room_details_are_for_members_only(anon, users, room):
    assert anon.get(f"/api/rooms/{room}", headers=users["bob"]).status_code == 403
    assert anon.get("/api/rooms/nowhere", headers=users["bob"]).status_code == 404


def test_an_invite_lets_someone_join_with_its_role(anon, users, room):
    invite = _invite(anon, users["alice"], "editor")
    assert invite.status_code == 201
    code = invite.json()["code"]

    joined = _join(anon, users["bob"], code)

    assert joined.json() == {"room_id": room, "role": "editor"}
    assert _members(anon, users["bob"]) == {"alice": "owner", "bob": "editor"}


def test_an_invite_can_be_used_by_several_people_and_twice(anon, users, room):
    code = _invite(anon, users["alice"], "viewer").json()["code"]

    assert _join(anon, users["bob"], code).status_code == 200
    assert _join(anon, users["carol"], code).status_code == 200
    assert _join(anon, users["bob"], code).json()["role"] == "viewer"  # reused: no duplicate
    assert _members(anon, users["alice"]) == {"alice": "owner", "bob": "viewer", "carol": "viewer"}


def test_joining_never_lowers_a_role(anon, users, room):
    _join(anon, users["bob"], _invite(anon, users["alice"], "editor").json()["code"])

    downgrade = _join(anon, users["bob"], _invite(anon, users["alice"], "viewer").json()["code"])
    owner = _join(anon, users["alice"], _invite(anon, users["alice"], "viewer").json()["code"])

    assert downgrade.json()["role"] == "editor"
    assert owner.json()["role"] == "owner"


def test_only_an_owner_can_invite(anon, users, room):
    _join(anon, users["bob"], _invite(anon, users["alice"], "editor").json()["code"])

    assert _invite(anon, users["bob"]).status_code == 403  # an editor
    assert _invite(anon, users["carol"]).status_code == 403  # not a member


@pytest.mark.parametrize(
    "body", [{"role": "owner"}, {"role": "admin"}, {"role": "editor", "expires_in_hours": 0}]
)
def test_an_invite_is_for_editor_or_viewer_and_some_hours(anon, users, room, body):
    response = anon.post(f"/api/rooms/{room}/invites", json=body, headers=users["alice"])
    assert response.status_code == 422


def test_an_expired_invite_is_refused(anon, users, room):
    code = _invite(anon, users["alice"], expires_in_hours=1).json()["code"]

    async def _expire():
        async with anon.app.state.sessions() as session:
            past = datetime.now(UTC) - timedelta(minutes=1)
            await session.execute(update(Invite).values(expires_at=past))
            await session.commit()

    anon.portal.call(_expire)
    response = _join(anon, users["bob"], code)
    assert (response.status_code, response.json()["detail"]) == (410, "this invite has expired")


def test_a_revoked_invite_is_refused(anon, users, room):
    code = _invite(anon, users["alice"]).json()["code"]

    assert anon.delete(f"/api/rooms/{room}/invites/{code}", headers=users["alice"]).status_code == 204
    response = _join(anon, users["bob"], code)

    assert (response.status_code, response.json()["detail"]) == (410, "this invite was revoked")


def test_only_an_owner_can_revoke_and_only_this_rooms_invites(anon, users, room):
    code = _invite(anon, users["alice"]).json()["code"]
    _join(anon, users["bob"], code)
    anon.post("/api/rooms", json={"room_id": "bobs"}, headers=users["bob"])

    assert anon.delete(f"/api/rooms/{room}/invites/{code}", headers=users["bob"]).status_code == 403
    assert anon.delete(f"/api/rooms/bobs/invites/{code}", headers=users["bob"]).status_code == 404


def test_an_unknown_code_is_404(anon, users, room):
    assert _join(anon, users["bob"], "not-a-code").status_code == 404


def test_only_the_codes_hash_is_stored(anon, users, room):
    code = _invite(anon, users["alice"]).json()["code"]

    async def _stored():
        async with anon.app.state.sessions() as session:
            return await session.scalar(select(Invite.code_hash))

    stored = anon.portal.call(_stored)
    assert code not in stored and len(stored) == 64


def test_an_owner_changes_roles(anon, users, room):
    _join(anon, users["bob"], _invite(anon, users["alice"], "editor").json()["code"])

    changed = anon.patch(f"/api/rooms/{room}/members/bob", json={"role": "viewer"}, headers=users["alice"])

    assert changed.json()["role"] == "viewer"
    assert _members(anon, users["alice"])["bob"] == "viewer"


def test_a_non_owner_cant_change_roles(anon, users, room):
    _join(anon, users["bob"], _invite(anon, users["alice"], "editor").json()["code"])

    response = anon.patch(f"/api/rooms/{room}/members/bob", json={"role": "owner"}, headers=users["bob"])

    assert response.status_code == 403


def test_the_last_owner_cant_step_down_or_leave(anon, users, room):
    demote = anon.patch(f"/api/rooms/{room}/members/alice", json={"role": "editor"}, headers=users["alice"])
    leave = anon.delete(f"/api/rooms/{room}/members/alice", headers=users["alice"])

    assert demote.status_code == leave.status_code == 409
    assert _members(anon, users["alice"]) == {"alice": "owner"}


def test_with_a_second_owner_the_first_can_leave(anon, users, room):
    _join(anon, users["bob"], _invite(anon, users["alice"], "editor").json()["code"])
    anon.patch(f"/api/rooms/{room}/members/bob", json={"role": "owner"}, headers=users["alice"])

    assert anon.delete(f"/api/rooms/{room}/members/alice", headers=users["alice"]).status_code == 204
    assert _members(anon, users["bob"]) == {"bob": "owner"}


def test_an_owner_removes_a_member(anon, users, room):
    _join(anon, users["bob"], _invite(anon, users["alice"], "editor").json()["code"])

    assert anon.delete(f"/api/rooms/{room}/members/bob", headers=users["alice"]).status_code == 204

    assert _members(anon, users["alice"]) == {"alice": "owner"}
    assert anon.get(f"/api/rooms/{room}", headers=users["bob"]).status_code == 403


def test_a_member_can_leave_but_not_remove_others(anon, users, room):
    code = _invite(anon, users["alice"], "editor").json()["code"]
    _join(anon, users["bob"], code)
    _join(anon, users["carol"], code)

    assert anon.delete(f"/api/rooms/{room}/members/carol", headers=users["bob"]).status_code == 403
    assert anon.delete(f"/api/rooms/{room}/members/bob", headers=users["bob"]).status_code == 204
    assert _members(anon, users["alice"]) == {"alice": "owner", "carol": "editor"}


def test_changing_someone_not_in_the_room_is_404(anon, users, room):
    path = f"/api/rooms/{room}/members"
    assert anon.patch(f"{path}/carol", json={"role": "viewer"}, headers=users["alice"]).status_code == 404
    assert anon.delete(f"{path}/nobody", headers=users["alice"]).status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/rooms"),
        ("GET", "/api/rooms"),
        ("GET", "/api/rooms/studio"),
        ("POST", "/api/rooms/studio/invites"),
        ("DELETE", "/api/rooms/studio/invites/abc"),
        ("POST", "/api/rooms/join/abc"),
        ("PATCH", "/api/rooms/studio/members/bob"),
        ("DELETE", "/api/rooms/studio/members/bob"),
    ],
)
def test_every_rooms_route_needs_a_token(anon, room, method, path):
    assert anon.request(method, path).status_code == 401
