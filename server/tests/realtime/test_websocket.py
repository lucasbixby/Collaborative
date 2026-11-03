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
from app.realtime.websocket import manager

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
        a.send_text(json.dumps(MOVE_AND_ROTATE))
        b.send_text(json.dumps(CREATE_CUBE))

        # If A's own batch were echoed back, it would arrive before B's.
        received = json.loads(a.receive_text())

    assert received == CREATE_CUBE


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

        assert json.loads(b.receive_text())["ops"][0]["mesh"]["vertices"] == [[0.5, 0.5, 0.5]] * count


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
