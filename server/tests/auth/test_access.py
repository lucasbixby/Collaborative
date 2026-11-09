"""Who may connect to a room's socket and send to it (#16, #17)."""

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from tests.accounts import bearer, ensure_room, token_for
from tests.catchup import read_catch_up
from tests.sync.test_conflicts import A, B, create, move


def _refusal(test_client, room_id, headers=None) -> tuple[int, str]:
    """Connect, and return the close code and reason the server ends the socket with."""
    with (
        test_client.websocket_connect(f"/ws/rooms/{room_id}", headers=headers or {}) as ws,
        pytest.raises(WebSocketDisconnect) as closed,
    ):
        ws.receive_text()
    return closed.value.code, closed.value.reason


def test_no_token_is_closed_with_4401(anon):
    assert _refusal(anon, "demo") == (4401, "sign in first")


@pytest.mark.parametrize(
    "header", ["Bearer not-a-token", "Basic YWxpY2U6cHc=", "Bearer ", "token-without-scheme"]
)
def test_a_bad_token_is_closed_with_4401(anon, header):
    code, _reason = _refusal(anon, "demo", {"Authorization": header})
    assert code == 4401


def test_a_token_in_the_query_string_is_ignored(anon):
    token = token_for(anon, "alice")
    with (
        anon.websocket_connect(f"/ws/rooms/demo?token={token}") as ws,
        pytest.raises(WebSocketDisconnect) as closed,
    ):
        ws.receive_text()
    assert closed.value.code == 4401


def test_a_valid_token_gets_catch_up(anon):
    alice = bearer(token_for(anon, "alice"))
    ensure_room(anon, "demo", alice)
    with anon.websocket_connect("/ws/rooms/demo", headers=alice) as ws:
        assert read_catch_up(ws) == ([], 0)


# -- Rooms and roles (#17) ----------------------------------------------------------------


@pytest.fixture
def studio(client):
    """Room "studio": tester (the client's own user) owns it, bob is an editor, vera a viewer,
    and mallory is signed up but not a member. Values are request headers."""
    people = {"owner": {}, "outsider": bearer(token_for(client, "mallory"))}
    ensure_room(client, "studio")
    for name, role in (("bob", "editor"), ("vera", "viewer")):
        people[role] = bearer(token_for(client, name))
        code = client.post("/api/rooms/studio/invites", json={"role": role}).json()["code"]
        assert client.post(f"/api/rooms/join/{code}", headers=people[role]).status_code == 200
    return people


def _connect(test_client, headers, room_id="studio"):
    return test_client.websocket_connect(f"/ws/rooms/{room_id}", headers=headers)


def _ops(*ops) -> str:
    return json.dumps({"v": 1, "type": "ops", "ops": list(ops)})


def test_a_non_member_is_closed_with_4403(client, studio):
    assert _refusal(client, "studio", studio["outsider"]) == (4403, "no access to room studio")


def test_a_room_that_doesnt_exist_looks_the_same_as_one_youre_not_in(client, studio):
    assert _refusal(client, "nowhere", studio["outsider"]) == (4403, "no access to room nowhere")


def test_a_viewer_gets_catch_up_and_live_ops_but_cant_edit(client, studio, read_log):
    with _connect(client, studio["owner"]) as owner, _connect(client, studio["editor"]) as watcher:
        read_catch_up(owner)
        read_catch_up(watcher)
        owner.send_text(_ops(create(lamport=1)))
        watcher.receive_text()  # logged, so the viewer's catch-up below has it
    with _connect(client, studio["viewer"]) as viewer, _connect(client, studio["owner"]) as owner:
        caught_up, _seq = read_catch_up(viewer)
        read_catch_up(owner)
        assert [message["ops"] for message in caught_up] == [[create(lamport=1)]]

        viewer.send_text(_ops(move(1.0, lamport=2, origin=B)))
        assert json.loads(viewer.receive_text()) == {
            "v": 1,
            "type": "error",
            "message": "viewers can't edit",
        }
        # The viewer's op wasn't relayed: the owner's next one is the first thing anyone gets.
        owner.send_text(_ops(move(2.0, lamport=3)))
        assert json.loads(viewer.receive_text())["ops"] == [move(2.0, lamport=3)]

    assert [json.loads(row.payload) for row in read_log(client, "studio")] == [
        create(lamport=1),
        move(2.0, lamport=3),
    ]


def test_an_editors_ops_relay(client, studio):
    with _connect(client, studio["editor"]) as editor, _connect(client, studio["viewer"]) as viewer:
        read_catch_up(editor)
        read_catch_up(viewer)
        editor.send_text(_ops(create(origin=B)))
        assert json.loads(viewer.receive_text())["ops"] == [create(origin=B)]


def test_another_user_cant_send_as_your_origin(client, studio):
    with _connect(client, studio["owner"]) as owner, _connect(client, studio["editor"]) as editor:
        read_catch_up(owner)
        read_catch_up(editor)
        owner.send_text(_ops(create(origin=A)))
        assert json.loads(editor.receive_text())["ops"] == [create(origin=A)]

        editor.send_text(_ops(move(1.0, origin=A, lamport=2)))  # copied off the relayed op

        error = json.loads(editor.receive_text())
        assert error == {"v": 1, "type": "error", "message": f"origin {A} belongs to another user"}
        owner.send_text(_ops(move(2.0, origin=A, lamport=3)))  # the owner isn't locked out
        assert json.loads(editor.receive_text())["ops"] == [move(2.0, origin=A, lamport=3)]


def test_the_owner_takes_its_origin_back_after_a_reconnect_but_others_cant(client, studio):
    with _connect(client, studio["owner"]) as first, _connect(client, studio["editor"]) as editor:
        read_catch_up(first)
        read_catch_up(editor)
        first.send_text(_ops(create(origin=A)))
        editor.receive_text()  # the create
        editor.send_text(_ops(move(1.0, origin=A, lamport=2)))
        assert "another user" in json.loads(editor.receive_text())["message"]
        # first's socket is still open: a dead socket nobody has noticed yet.
        with _connect(client, studio["owner"]) as reconnected:
            read_catch_up(reconnected)
            reconnected.send_text(_ops(move(3.0, origin=A, lamport=3)))
            assert json.loads(editor.receive_text())["ops"] == [move(3.0, origin=A, lamport=3)]
            first.receive_text()  # it still hears the room, before it's found dead


def test_origin_ownership_survives_a_restart(database_url):
    with TestClient(create_app(database_url)) as first:
        alice = bearer(token_for(first, "alice"))
        bob = bearer(token_for(first, "bob"))
        ensure_room(first, "studio", alice)
        code = first.post("/api/rooms/studio/invites", json={"role": "editor"}, headers=alice)
        first.post(f"/api/rooms/join/{code.json()['code']}", headers=bob)
        with _connect(first, alice) as ws:
            read_catch_up(ws)
            ws.send_text(_ops(create(origin=A)))

    with TestClient(create_app(database_url)) as second, _connect(second, bob) as ws:
        read_catch_up(ws)
        ws.send_text(_ops(move(1.0, origin=A, lamport=2)))
        assert "another user" in json.loads(ws.receive_text())["message"]


def test_a_removed_member_is_disconnected_with_4403(client, studio):
    with _connect(client, studio["editor"]) as editor:
        read_catch_up(editor)

        assert client.delete("/api/rooms/studio/members/bob").status_code == 204

        with pytest.raises(WebSocketDisconnect) as closed:
            editor.receive_text()
        assert (closed.value.code, closed.value.reason) == (4403, "removed from room studio")
    assert _refusal(client, "studio", studio["editor"])[0] == 4403


def test_others_keep_working_after_a_member_is_removed(client, studio):
    with (
        _connect(client, studio["owner"]) as owner,
        _connect(client, studio["viewer"]) as viewer,
        _connect(client, studio["editor"]) as editor,
    ):
        for ws in (owner, viewer, editor):
            read_catch_up(ws)
        client.delete("/api/rooms/studio/members/bob")
        with pytest.raises(WebSocketDisconnect):
            editor.receive_text()

        owner.send_text(_ops(create()))
        assert json.loads(viewer.receive_text())["ops"] == [create()]


def test_a_downgraded_editor_stays_connected_but_cant_edit(client, studio):
    with _connect(client, studio["editor"]) as editor, _connect(client, studio["owner"]) as owner:
        read_catch_up(editor)
        read_catch_up(owner)
        editor.send_text(_ops(create(origin=B)))
        owner.receive_text()

        changed = client.patch("/api/rooms/studio/members/bob", json={"role": "viewer"})
        assert changed.status_code == 200

        editor.send_text(_ops(move(1.0, origin=B, lamport=2)))
        assert json.loads(editor.receive_text())["message"] == "viewers can't edit"
        owner.send_text(_ops(move(2.0, lamport=3)))
        assert json.loads(editor.receive_text())["ops"] == [move(2.0, lamport=3)]


def test_an_upgraded_viewer_can_edit_at_once(client, studio):
    with _connect(client, studio["viewer"]) as viewer, _connect(client, studio["owner"]) as owner:
        read_catch_up(viewer)
        read_catch_up(owner)

        client.patch("/api/rooms/studio/members/vera", json={"role": "editor"})

        viewer.send_text(_ops(create(origin=B)))
        assert json.loads(owner.receive_text())["ops"] == [create(origin=B)]
