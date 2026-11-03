"""Tests for the WebSocket relay (#11): rooms, broadcast, and rejection.

`TestClient.websocket_connect` has no clean "this client received nothing" timeout, so
absence is proved by ordering instead: have another client send a second message and
check it's the first thing the client under test receives. If the thing being ruled out
(an echo, a leak into another room, a broadcast error) had happened, it would have
arrived first.
"""

import copy
import json
import logging
import re
import uuid
from pathlib import Path

import pytest
from starlette.websockets import WebSocketDisconnect

from app.config import settings
from app.realtime.websocket import manager, origins

PROTOCOL_MD = Path(__file__).resolve().parents[3] / "docs" / "protocol.md"


def _example_messages() -> list[dict]:
    """The example `ops` messages in docs/protocol.md, in the order they appear."""
    text = PROTOCOL_MD.read_text(encoding="utf-8")
    blocks = [json.loads(block) for block in re.findall(r"```json\n(.*?)```", text, re.DOTALL)]
    return [block for block in blocks if block.get("type") == "ops"]


EXAMPLES = _example_messages()
MOVE_AND_ROTATE = EXAMPLES[0]  # a `set` batch: location + rotation
CREATE_CUBE = EXAMPLES[1]
DELETE_CUBE = EXAMPLES[2]
OTHER_ORIGIN = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def _as_origin(message, origin):
    """A copy of `message` with every op claiming `origin`, as another client would send it."""
    message = copy.deepcopy(message)
    for op in message["ops"]:
        op["origin"] = origin
    return message


def _ws(client, room_id):
    return client.websocket_connect(f"/ws/rooms/{room_id}")


@pytest.fixture
def room():
    """A factory for fresh, unique room ids.

    `manager` (app.realtime.websocket) is one instance shared by the whole test process,
    so two tests reusing a literal room name like "room-a" can race: if a previous test's
    socket hasn't finished being removed yet, a broadcast in this test can try to send to
    it and hang (observed empirically, ~10% of runs, with a shared literal room name). A
    fresh id per test makes that race impossible rather than just unlikely.
    """

    def make(label: str = "room") -> str:
        return f"{label}-{uuid.uuid4().hex[:8]}"

    return make


def test_a_valid_batch_reaches_b_unchanged(client, room):
    room_id = room()
    with _ws(client, room_id) as a, _ws(client, room_id) as b:
        a.send_text(json.dumps(MOVE_AND_ROTATE))

        received = json.loads(b.receive_text())

    assert received == MOVE_AND_ROTATE


def test_sender_never_gets_its_own_message_back(client, room):
    room_id = room()
    with _ws(client, room_id) as a, _ws(client, room_id) as b:
        from_b = _as_origin(CREATE_CUBE, OTHER_ORIGIN)
        a.send_text(json.dumps(MOVE_AND_ROTATE))
        b.send_text(json.dumps(from_b))

        # If A's own batch were echoed back, it would arrive before B's.
        received = json.loads(a.receive_text())

    assert received == from_b


def test_a_client_in_another_room_gets_nothing(client, room):
    room_a, room_b = room("a"), room("b")
    with _ws(client, room_a) as a, _ws(client, room_a) as b, _ws(client, room_b) as c:
        a.send_text(json.dumps(MOVE_AND_ROTATE))
        assert json.loads(b.receive_text()) == MOVE_AND_ROTATE  # the room_a relay; not c's

        with _ws(client, room_b) as d:
            d.send_text(json.dumps(CREATE_CUBE))
            # If anything from room_a had leaked into room_b, it would arrive before this.
            received = json.loads(c.receive_text())

    assert received == CREATE_CUBE


def test_invalid_message_gets_an_error_to_the_sender_only(client, room):
    room_id = room()
    with _ws(client, room_id) as a, _ws(client, room_id) as b:
        bad = copy.deepcopy(MOVE_AND_ROTATE)
        bad["ops"][0]["lamport"] = 0  # the schema requires lamport >= 1
        a.send_text(json.dumps(bad))

        error = json.loads(a.receive_text())
        assert error["type"] == "error"
        assert isinstance(error["message"], str) and error["message"]

        # The connection is still open, and B never got the error (or anything else).
        a.send_text(json.dumps(CREATE_CUBE))
        received = json.loads(b.receive_text())

    assert received == CREATE_CUBE


def test_oversized_message_gets_an_error_and_connection_stays_open(client, room):
    room_id = room()
    with _ws(client, room_id) as a, _ws(client, room_id) as b:
        oversized = "x" * (settings.max_operation_bytes + 1)
        a.send_text(oversized)

        error = json.loads(a.receive_text())
        assert error["type"] == "error"

        a.send_text(json.dumps(DELETE_CUBE))
        received = json.loads(b.receive_text())

    assert received == DELETE_CUBE


def _create_with_bad(**changes):
    """The example `create`, with some of its fields replaced."""
    message = copy.deepcopy(CREATE_CUBE)
    message["ops"][0].update(changes)
    return message


def _create_without(field):
    message = copy.deepcopy(CREATE_CUBE)
    del message["ops"][0][field]
    return message


def _create_with_vertices(count):
    message = copy.deepcopy(CREATE_CUBE)
    message["ops"][0]["mesh"] = {"vertices": [[0.5, 0.5, 0.5]] * count, "faces": []}
    return message


@pytest.mark.parametrize(
    "bad",
    [
        _create_with_bad(object_type="EMPTY"),
        _create_with_bad(object="Cube"),
        _create_with_bad(mesh={"vertices": [[0, 0, 0]], "faces": [[0, 1, 2]]}),
        _create_with_bad(mesh={"vertices": [[0, 0]], "faces": []}),
        _create_with_bad(parent="9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d"),
        _create_without("mesh"),
        _create_without("transform"),
        _create_with_vertices(5000),  # valid but oversized
    ],
    ids=[
        "non-mesh-type",
        "name-as-id",
        "face-index-out-of-range",
        "short-vertex",
        "unknown-field",
        "no-mesh",
        "no-transform",
        "oversized",
    ],
)
def test_bad_create_gets_an_error_and_is_not_forwarded(client, room, bad):
    room_id = room()
    with _ws(client, room_id) as a, _ws(client, room_id) as b:
        a.send_text(json.dumps(bad))

        assert json.loads(a.receive_text())["type"] == "error"

        # If the bad create had been forwarded, it would arrive before this.
        a.send_text(json.dumps(DELETE_CUBE))
        assert json.loads(b.receive_text()) == DELETE_CUBE


def test_largest_create_that_fits_is_relayed(client, room):
    # The add-on measures a `create` with `json.dumps` before sending (detect.py); that
    # number must agree with the limit enforced here, or it would send what's refused here.
    count = 1
    while len(json.dumps(_create_with_vertices(count + 1))) <= settings.max_operation_bytes:
        count += 1
    message = _create_with_vertices(count)

    room_id = room()
    with _ws(client, room_id) as a, _ws(client, room_id) as b:
        a.send_text(json.dumps(message))

        assert (
            json.loads(b.receive_text())["ops"][0]["mesh"]["vertices"] == [[0.5, 0.5, 0.5]] * count
        )


# -- Origin checks (#10) ------------------------------------------------------------------


def test_spoofed_origin_gets_an_error_and_is_not_forwarded(client, room):
    room_id = room()
    with _ws(client, room_id) as a, _ws(client, room_id) as b:
        a.send_text(json.dumps(MOVE_AND_ROTATE))  # pins A's origin
        assert json.loads(b.receive_text()) == MOVE_AND_ROTATE

        a.send_text(json.dumps(_as_origin(MOVE_AND_ROTATE, OTHER_ORIGIN)))
        error = json.loads(a.receive_text())
        assert error["type"] == "error"
        assert OTHER_ORIGIN in error["message"]

        # The connection is still open, and this is the first thing B has received since.
        a.send_text(json.dumps(DELETE_CUBE))
        assert json.loads(b.receive_text()) == DELETE_CUBE


def test_mixed_origin_batch_gets_an_error_and_does_not_pin(client, room):
    room_id = room()
    with _ws(client, room_id) as a, _ws(client, room_id) as b:
        mixed = copy.deepcopy(MOVE_AND_ROTATE)
        mixed["ops"][1]["origin"] = OTHER_ORIGIN
        a.send_text(json.dumps(mixed))
        assert json.loads(a.receive_text())["type"] == "error"

        # Neither of those origins got pinned, so A can still send as a third one.
        third = _as_origin(DELETE_CUBE, "dddddddd-dddd-4ddd-8ddd-dddddddddddd")
        a.send_text(json.dumps(third))
        assert json.loads(b.receive_text()) == third


def test_two_clients_with_different_origins_both_relay(client, room):
    room_id = room()
    from_b = _as_origin(DELETE_CUBE, OTHER_ORIGIN)
    with _ws(client, room_id) as a, _ws(client, room_id) as b:
        a.send_text(json.dumps(MOVE_AND_ROTATE))
        assert json.loads(b.receive_text()) == MOVE_AND_ROTATE
        b.send_text(json.dumps(from_b))
        assert json.loads(a.receive_text()) == from_b
        a.send_text(json.dumps(MOVE_AND_ROTATE))
        assert json.loads(b.receive_text()) == MOVE_AND_ROTATE


def test_reconnect_with_the_same_origin_after_a_clean_disconnect(client, room):
    room_id = room()
    with _ws(client, room_id) as b:
        with _ws(client, room_id) as a:
            a.send_text(json.dumps(MOVE_AND_ROTATE))
            assert json.loads(b.receive_text()) == MOVE_AND_ROTATE

        with _ws(client, room_id) as a_again:
            a_again.send_text(json.dumps(DELETE_CUBE))
            assert json.loads(b.receive_text()) == DELETE_CUBE


def test_reconnect_while_the_old_socket_still_looks_alive(client, room, caplog):
    # D-062: `stale` is never closed, exactly what the server sees when a network drops with
    # no FIN. The add-on's new connection must work straight away, not after keepalive.
    room_id = room()
    with _ws(client, room_id) as b, _ws(client, room_id) as stale:
        stale.send_text(json.dumps(MOVE_AND_ROTATE))
        assert json.loads(b.receive_text()) == MOVE_AND_ROTATE

        with _ws(client, room_id) as reconnected:
            reconnected.send_text(json.dumps(CREATE_CUBE))
            assert json.loads(b.receive_text()) == CREATE_CUBE
            assert "origin takeover" in caplog.text

            # They never share it: the old connection is refused, and stays open (D-064).
            assert json.loads(stale.receive_text()) == CREATE_CUBE  # still gets broadcasts
            stale.send_text(json.dumps(MOVE_AND_ROTATE))
            assert json.loads(stale.receive_text())["type"] == "error"

            reconnected.send_text(json.dumps(DELETE_CUBE))
            assert json.loads(b.receive_text()) == DELETE_CUBE  # the refused one wasn't relayed


def test_old_socket_dying_after_a_takeover_leaves_the_new_connection_working(client, room):
    room_id = room()
    with _ws(client, room_id) as b, _ws(client, room_id) as reconnected:
        with _ws(client, room_id) as stale:
            stale.send_text(json.dumps(MOVE_AND_ROTATE))
            assert json.loads(b.receive_text()) == MOVE_AND_ROTATE
            reconnected.send_text(json.dumps(CREATE_CUBE))
            assert json.loads(b.receive_text()) == CREATE_CUBE
        # `stale`'s release ran when it closed. Had it freed the origin, this would be
        # refused, because `reconnected` no longer holds it.
        reconnected.send_text(json.dumps(DELETE_CUBE))
        assert json.loads(b.receive_text()) == DELETE_CUBE


def test_disconnect_releases_the_origin(client, room):
    room_id = room()
    with _ws(client, room_id) as a:
        a.send_text(json.dumps(MOVE_AND_ROTATE))
        a.send_text(json.dumps(_as_origin(MOVE_AND_ROTATE, OTHER_ORIGIN)))
        assert json.loads(a.receive_text())["type"] == "error"  # so the pin has happened
        assert [key for key in origins._holders if key[0] == room_id]

    assert not [key for key in origins._holders if key[0] == room_id]
    assert not [key for key in origins._pins if key[0] == room_id]


def test_an_unexpected_exception_cannot_leak_a_pinned_origin(client, room, monkeypatch):
    async def broken_broadcast(*_args, **_kwargs):
        raise RuntimeError("broadcast failed")

    monkeypatch.setattr(manager, "broadcast", broken_broadcast)
    room_id = room()

    with pytest.raises(RuntimeError, match="broadcast failed"), _ws(client, room_id) as a:
        a.send_text(json.dumps(MOVE_AND_ROTATE))
        a.receive_text()

    assert not [key for key in origins._pins if key[0] == room_id]
    assert not [key for key in origins._holders if key[0] == room_id]


def test_three_clients_fan_out_to_the_other_two(client, room):
    room_id = room()
    with _ws(client, room_id) as a, _ws(client, room_id) as b, _ws(client, room_id) as c:
        a.send_text(json.dumps(MOVE_AND_ROTATE))

        assert json.loads(b.receive_text()) == MOVE_AND_ROTATE
        assert json.loads(c.receive_text()) == MOVE_AND_ROTATE


def test_disconnect_leaves_others_working_and_empties_the_room(client, room):
    room_id = room("solo")
    with _ws(client, room_id) as a:
        with _ws(client, room_id):
            pass  # the second client disconnects here; A is unaffected

        with _ws(client, room_id) as c:
            c.send_text(json.dumps(MOVE_AND_ROTATE))
            assert json.loads(a.receive_text()) == MOVE_AND_ROTATE

    assert room_id not in manager._rooms  # A and C have both left too


def test_bad_room_id_is_refused(client):
    with pytest.raises(WebSocketDisconnect) as exc_info, _ws(client, "bad room!"):
        pass

    assert exc_info.value.code == 1008


def test_connect_is_logged(client, room, caplog):
    room_id = room()
    caplog.set_level(logging.INFO, logger="app.realtime.websocket")

    with _ws(client, room_id):
        pass

    assert f"connect room={room_id} clients=1" in caplog.text
