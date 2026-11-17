"""Tests for save approval: a guest's save in Blender becomes a request the host answers."""

import json

import pytest

from app.realtime import saves
from tests.accounts import bearer, ensure_room, join, token_for
from tests.catchup import read_catch_up

ROOM = "studio"
SAVE_REQUEST = json.dumps({"v": 1, "type": "save_request"})


@pytest.fixture
def people(client):
    """Headers for bob (editor) and vera (viewer) in "studio", which tester hosts."""
    ensure_room(client, ROOM)
    headers = {name: bearer(token_for(client, name)) for name in ("bob", "vera", "mallory")}
    join(client, ROOM, headers["bob"])
    join(client, ROOM, headers["vera"], "viewer")
    return headers


def _connect(client, headers=None):
    ws = client.websocket_connect(f"/ws/rooms/{ROOM}", headers=headers or {})
    return ws


def _pending(client, headers=None):
    rooms = client.get("/api/rooms", headers=headers or {}).json()
    return next(room for room in rooms if room["room_id"] == ROOM)["save_requests"]


def _answer(client, request_id, approve, headers=None):
    return client.post(
        f"/api/rooms/{ROOM}/save-requests/{request_id}", json={"approve": approve}, headers=headers or {}
    )


def test_a_guests_save_becomes_a_request_only_the_host_sees(client, people):
    with _connect(client, people["bob"]) as guest:
        read_catch_up(guest)
        guest.send_text(SAVE_REQUEST)
        assert json.loads(guest.receive_text()) == {"v": 1, "type": "save_pending"}

        pending = _pending(client)
        assert [request["username"] for request in pending] == ["bob"]
        assert _pending(client, people["bob"]) == []


def test_approving_tells_the_hosts_blender_to_save_and_the_guest_the_answer(client, people):
    with _connect(client) as host, _connect(client, people["bob"]) as guest:
        read_catch_up(host)
        read_catch_up(guest)
        guest.send_text(SAVE_REQUEST)
        guest.receive_text()

        answered = _answer(client, _pending(client)[0]["id"], True)

        assert answered.status_code == 204
        assert json.loads(host.receive_text()) == {"v": 1, "type": "save", "requested_by": "bob"}
        assert json.loads(guest.receive_text()) == {
            "v": 1,
            "type": "save_result",
            "approved": True,
            "by": "tester",
        }
        assert _pending(client) == []


def test_denying_saves_nothing_and_tells_the_guest(client, people):
    with _connect(client) as host, _connect(client, people["bob"]) as guest:
        read_catch_up(host)
        read_catch_up(guest)
        guest.send_text(SAVE_REQUEST)
        guest.receive_text()

        assert _answer(client, _pending(client)[0]["id"], False).status_code == 204

        assert json.loads(guest.receive_text())["approved"] is False
        assert _pending(client) == []
        # The host's Blender heard nothing: the next thing it receives is this error reply.
        host.send_text("not json")
        assert json.loads(host.receive_text())["type"] == "error"


def test_approving_without_the_room_open_in_blender_is_409_and_keeps_the_request(client, people):
    with _connect(client, people["bob"]) as guest:
        read_catch_up(guest)
        guest.send_text(SAVE_REQUEST)
        guest.receive_text()
        request_id = _pending(client)[0]["id"]

        refused = _answer(client, request_id, True)

        assert refused.status_code == 409 and "Blender" in refused.json()["detail"]
        assert [request["id"] for request in _pending(client)] == [request_id]


def test_only_the_host_answers(client, people):
    with _connect(client, people["bob"]) as guest:
        read_catch_up(guest)
        guest.send_text(SAVE_REQUEST)
        guest.receive_text()
        request_id = _pending(client)[0]["id"]

        assert _answer(client, request_id, True, people["bob"]).status_code == 403
        assert _answer(client, request_id, True, people["mallory"]).status_code == 403
        assert _answer(client, "no-such-request", True).status_code == 404


def test_saving_twice_leaves_one_request(client, people):
    with _connect(client, people["bob"]) as guest:
        read_catch_up(guest)
        for _ in range(2):
            guest.send_text(SAVE_REQUEST)
            guest.receive_text()
        assert len(_pending(client)) == 1


def test_the_hosts_own_save_needs_no_request_and_a_viewer_has_nothing_to_save(client, people):
    with _connect(client) as host, _connect(client, people["vera"]) as viewer:
        read_catch_up(host)
        read_catch_up(viewer)
        host.send_text(SAVE_REQUEST)
        viewer.send_text(SAVE_REQUEST)

        assert json.loads(viewer.receive_text()) == {
            "v": 1,
            "type": "error",
            "message": "viewers can't edit",
        }
        assert _pending(client) == []


def test_a_removed_guests_request_goes_with_them(client, people):
    with _connect(client, people["bob"]) as guest:
        read_catch_up(guest)
        guest.send_text(SAVE_REQUEST)
        guest.receive_text()
        client.delete(f"/api/rooms/{ROOM}/members/bob")
        assert _pending(client) == []


def test_an_unanswered_request_expires():
    now = [1000.0]
    requests = saves.SaveRequests(clock=lambda: now[0])
    first = requests.add("studio", 2, "bob")
    now[0] += saves.EXPIRES_AFTER - 1
    assert requests.pending("studio") == [first]
    now[0] += 1
    assert requests.pending("studio") == []
    assert requests.take("studio", first.id) is None
