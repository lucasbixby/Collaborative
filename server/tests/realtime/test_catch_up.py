"""Tests for catch-up on connect (#20) and the REST endpoints over the same state."""

import json
import threading
import time
import uuid

from app.config import settings
from app.sync import log as operation_log
from app.sync.conflicts import RoomState
from app.sync.operations import parse_message
from tests.catchup import joined, read_catch_up
from tests.sync.test_conflicts import A, B, X, Y, create, delete, move

Z = "33333333-3333-4333-8333-333333333333"


def _room() -> str:
    return f"room-{uuid.uuid4().hex[:8]}"


def _ops(*ops) -> str:
    return json.dumps({"v": 1, "type": "ops", "ops": list(ops)})


def _received_ops(messages) -> list[dict]:
    return [op for message in messages for op in message["ops"]]


def test_a_new_client_gets_catch_up_then_synced_then_live_ops(client):
    room = _room()
    with joined(client, room) as a, joined(client, room) as b:
        a.send_text(_ops(create(lamport=1)))
        b.receive_text()
        a.send_text(_ops(move(1.0, lamport=2)))
        b.receive_text()

        with client.websocket_connect(f"/ws/rooms/{room}") as c:
            first = json.loads(c.receive_text())
            second = json.loads(c.receive_text())
            synced = json.loads(c.receive_text())
            a.send_text(_ops(move(2.0, lamport=3)))
            live = json.loads(c.receive_text())

    assert first["ops"] == [create(lamport=1)]
    assert second["ops"] == [move(1.0, lamport=2)]
    assert synced["type"] == "synced"
    assert synced["seq"] > 0
    assert live["ops"] == [move(2.0, lamport=3)]


def test_an_empty_room_sends_only_synced_at_seq_0(client):
    with client.websocket_connect(f"/ws/rooms/{_room()}") as ws:
        assert json.loads(ws.receive_text()) == {"v": 1, "type": "synced", "seq": 0}


def test_synced_seq_is_the_last_logged_seq(client, read_log):
    room = _room()
    with joined(client, room) as a, joined(client, room) as b:
        a.send_text(_ops(create(lamport=1), move(1.0, lamport=2)))
        b.receive_text()
    with joined(client, room) as c:
        assert c.synced_seq == read_log(client, room)[-1].seq


def test_a_client_that_was_away_converges_with_the_room(client):
    # B leaves; A moves one object, deletes another and creates a third; B comes back.
    room = _room()
    with joined(client, room) as a, joined(client, room) as watcher:
        with joined(client, room) as b:
            a.send_text(_ops(create(obj=X, lamport=1)))
            b.receive_text()
            a.send_text(_ops(create(obj=Y, lamport=2)))
            b.receive_text()
            watcher.receive_text()
            watcher.receive_text()
            b_seen = RoomState().apply_all(op for m in b.catch_up for op in m["ops"])
            b_seen.apply_all([create(obj=X, lamport=1), create(obj=Y, lamport=2)])

        a.send_text(_ops(move(5.0, obj=X, lamport=3)))
        a.send_text(_ops(delete(obj=Y, lamport=4)))
        a.send_text(_ops(create(obj=Z, lamport=5)))
        for _ in range(3):  # all three are logged before B comes back
            watcher.receive_text()

        with joined(client, room) as b_again:
            missed = _received_ops(b_again.catch_up)

    # B applies the catch-up over what it already had, as the add-on does.
    assert b_seen.apply_all(missed) == RoomState().apply_all(
        [
            create(obj=X, lamport=1),
            create(obj=Z, lamport=5),
            move(5.0, obj=X, lamport=3),
            delete(obj=Y, lamport=4),
        ]
    )
    assert missed == [
        create(obj=X, lamport=1),
        create(obj=Z, lamport=5),
        move(5.0, obj=X, lamport=3),
        delete(obj=Y, lamport=4),
    ]


def test_every_catch_up_message_fits_has_one_origin_and_parses(client):
    room = _room()
    big = create(obj=X, lamport=1)
    big["mesh"]["vertices"] = [[0.123456, 0.654321, 0.111111]] * 1500
    objects = [f"{n:08x}-0000-4000-8000-000000000000" for n in range(2000)]

    async def _fill():
        async with client.app.state.sessions() as session:
            await operation_log.append(session, room, parse_message(_ops(big)))
            for origin in (A, B):
                ops = [
                    move(float(n), obj=obj, lamport=n + 2, origin=origin)
                    for n, obj in enumerate(objects)
                ]
                for start in range(0, len(ops), 250):
                    await operation_log.append(
                        session, room, parse_message(_ops(*ops[start : start + 250]))
                    )

    client.portal.call(_fill)
    with joined(client, room) as ws:
        messages = ws.catch_up

    assert len(messages) > 3
    for message in messages:
        text = json.dumps(message, separators=(",", ":"))
        assert len(text.encode("utf-8")) <= settings.max_operation_bytes
        parse_message(text)
    assert sum(len(m["ops"]) for m in messages) == 1 + len(objects)


def _wait_until_logged(client, room, count, timeout=10.0):
    """Wait for the server to work through a client's backlog. Leaving while it's still
    appending can overlap the app's shutdown, and the test then hangs in teardown."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with client.websocket_connect(f"/ws/rooms/{room}") as ws:
            if len(_received_ops(read_catch_up(ws)[0])) >= count:
                return
        time.sleep(0.02)
    raise AssertionError(f"the server didn't log {count} ops within {timeout}s")


def test_an_op_sent_while_a_client_connects_is_never_lost(client):
    # A streams deletes for distinct IDs (so the fold can't merge them) while C connects
    # again and again. Each time, C's catch-up must hold an unbroken run of A's deletes,
    # and the first live op after it must be the next one: no gap between the two.
    room = _room()
    stop = threading.Event()

    def _index(op) -> int:
        return op["lamport"] - 1

    with joined(client, room) as a:
        sent = []

        def _send():
            while not stop.is_set() and len(sent) < 2000:
                n = len(sent)
                a.send_text(_ops(delete(obj=str(uuid.UUID(int=n + 1)), lamport=n + 1)))
                sent.append(n)
                time.sleep(0.0005)

        sender = threading.Thread(target=_send)
        sender.start()
        overlaps = []
        try:
            for _ in range(20):
                with client.websocket_connect(f"/ws/rooms/{room}") as c:
                    catch_up, _seq = read_catch_up(c)
                    seen = sorted(_index(op) for op in _received_ops(catch_up))
                    first_live = _index(json.loads(c.receive_text())["ops"][0])
                overlaps.append(len(seen))
                assert seen == list(range(len(seen))), "a gap inside the catch-up"
                assert first_live == len(seen), (
                    f"after {len(seen)} caught up, live was {first_live}"
                )
        finally:
            stop.set()
            sender.join()
            _wait_until_logged(client, room, len(sent))

    assert any(overlaps), "every connection came before A's first op"
    assert len(set(overlaps)) > 1, "A wasn't sending while C connected"


# -- REST ---------------------------------------------------------------------------------


def test_rest_snapshot_matches_what_a_joining_client_gets(client):
    room = _room()
    with joined(client, room) as a, joined(client, room) as b:
        a.send_text(_ops(create(lamport=1)))
        b.receive_text()
        a.send_text(_ops(move(1.0, lamport=2), delete(obj=Y, lamport=3)))
        b.receive_text()
    with joined(client, room) as c:
        caught_up, seq = _received_ops(c.catch_up), c.synced_seq

    body = client.get(f"/api/rooms/{room}/snapshot").json()

    assert body["room_id"] == room
    assert body["seq"] == seq
    assert sorted(map(json.dumps, body["ops"])) == sorted(map(json.dumps, caught_up))


def test_rest_snapshot_of_an_unknown_room_is_empty(client):
    assert client.get("/api/rooms/nobody-here/snapshot").json() == {
        "room_id": "nobody-here",
        "seq": 0,
        "ops": [],
    }


def test_rest_operations_pages_by_seq(client, read_log):
    room = _room()
    with joined(client, room) as a, joined(client, room) as b:
        a.send_text(_ops(create(lamport=1), move(1.0, lamport=2), move(2.0, lamport=3)))
        b.receive_text()
    seqs = [row.seq for row in read_log(client, room)]

    first = client.get(f"/api/rooms/{room}/operations", params={"limit": 2}).json()
    rest = client.get(
        f"/api/rooms/{room}/operations", params={"since": first["operations"][-1]["seq"]}
    ).json()

    assert [row["seq"] for row in first["operations"]] == seqs[:2]
    assert [row["seq"] for row in rest["operations"]] == seqs[2:]
    assert [row["op"] for row in first["operations"] + rest["operations"]] == [
        create(lamport=1),
        move(1.0, lamport=2),
        move(2.0, lamport=3),
    ]
    assert first["operations"][0]["received_at"]


def test_rest_refuses_a_bad_room_id_and_bad_paging(client):
    assert client.get("/api/rooms/bad%20room/snapshot").status_code == 422
    assert client.get("/api/rooms/bad%20room/operations").status_code == 422
    assert client.get(f"/api/rooms/{'x' * 65}/snapshot").status_code == 422
    assert client.get("/api/rooms/ok/operations", params={"since": -1}).status_code == 422
    assert client.get("/api/rooms/ok/operations", params={"limit": 0}).status_code == 422
    assert client.get("/api/rooms/ok/operations", params={"limit": 1001}).status_code == 422
