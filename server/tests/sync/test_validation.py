"""Tests for origin checks (#10): one origin per message, and `OriginRegistry`."""

import copy
import json
import re
from pathlib import Path

import pytest

from app.sync.operations import parse_message
from app.sync.validation import OriginRegistry

PROTOCOL_MD = Path(__file__).resolve().parents[3] / "docs" / "protocol.md"
ROOM = "room"
OTHER_ROOM = "other-room"
ORIGIN_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ORIGIN_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
CONN_1, CONN_2, CONN_3 = 1, 2, 3


def _batch_of_two() -> dict:
    """The first example in docs/protocol.md: a batch of two ops with one origin."""
    text = PROTOCOL_MD.read_text(encoding="utf-8")
    blocks = [json.loads(block) for block in re.findall(r"```json\n(.*?)```", text, re.DOTALL)]
    return next(block for block in blocks if block.get("type") == "ops")


@pytest.fixture
def registry() -> OriginRegistry:
    return OriginRegistry()


# -- One origin per message ---------------------------------------------------------------


def test_batch_with_one_origin_parses_and_exposes_it():
    message = _batch_of_two()

    assert parse_message(json.dumps(message)).origin == message["ops"][0]["origin"]


def test_mixed_origin_batch_is_rejected_naming_both():
    message = copy.deepcopy(_batch_of_two())
    message["ops"][0]["origin"] = ORIGIN_A
    message["ops"][1]["origin"] = ORIGIN_B

    with pytest.raises(ValueError, match="one origin") as exc_info:
        parse_message(json.dumps(message))

    assert ORIGIN_A in str(exc_info.value)
    assert ORIGIN_B in str(exc_info.value)


# -- Pinning ------------------------------------------------------------------------------


def test_first_message_pins_and_the_same_origin_keeps_working(registry):
    registry.check(ROOM, CONN_1, ORIGIN_A)
    registry.check(ROOM, CONN_1, ORIGIN_A)


def test_a_different_origin_later_is_rejected(registry):
    registry.check(ROOM, CONN_1, ORIGIN_A)

    with pytest.raises(ValueError, match=f"sends as origin {ORIGIN_A}, not {ORIGIN_B}"):
        registry.check(ROOM, CONN_1, ORIGIN_B)

    registry.check(ROOM, CONN_1, ORIGIN_A)  # the rejection didn't change the pin


def test_different_origins_in_one_room_coexist(registry):
    registry.check(ROOM, CONN_1, ORIGIN_A)
    registry.check(ROOM, CONN_2, ORIGIN_B)

    registry.check(ROOM, CONN_1, ORIGIN_A)
    registry.check(ROOM, CONN_2, ORIGIN_B)


def test_same_origin_in_two_rooms_is_allowed(registry):
    registry.check(ROOM, CONN_1, ORIGIN_A)
    registry.check(OTHER_ROOM, CONN_2, ORIGIN_A)

    registry.check(ROOM, CONN_1, ORIGIN_A)
    registry.check(OTHER_ROOM, CONN_2, ORIGIN_A)


def test_release_frees_the_origin_without_a_takeover(registry, caplog):
    registry.check(ROOM, CONN_1, ORIGIN_A)

    registry.release(ROOM, CONN_1)
    registry.check(ROOM, CONN_2, ORIGIN_A)

    assert "takeover" not in caplog.text


def test_release_of_a_connection_that_never_pinned_is_safe(registry):
    registry.release(ROOM, CONN_1)


def test_release_leaves_nothing_behind(registry):
    registry.check(ROOM, CONN_1, ORIGIN_A)
    registry.check(ROOM, CONN_2, ORIGIN_A)  # a takeover, so both have entries

    registry.release(ROOM, CONN_1)
    registry.release(ROOM, CONN_2)

    assert registry._pins == {}
    assert registry._holders == {}


# -- Reconnect takeover (D-062) -----------------------------------------------------------


def test_new_connection_takes_over_while_the_old_one_still_looks_alive(registry, caplog):
    registry.check(ROOM, CONN_1, ORIGIN_A)  # this socket has died, but nobody has noticed

    registry.check(ROOM, CONN_2, ORIGIN_A)  # the add-on's reconnect

    assert f"origin takeover room={ROOM} origin={ORIGIN_A}" in caplog.text


def test_two_connections_never_share_an_origin(registry):
    registry.check(ROOM, CONN_1, ORIGIN_A)
    registry.check(ROOM, CONN_2, ORIGIN_A)

    with pytest.raises(ValueError, match="newer connection"):
        registry.check(ROOM, CONN_1, ORIGIN_A)

    registry.check(ROOM, CONN_2, ORIGIN_A)


def test_the_stale_connection_dying_late_does_not_free_the_origin(registry):
    registry.check(ROOM, CONN_1, ORIGIN_A)
    registry.check(ROOM, CONN_2, ORIGIN_A)

    registry.release(ROOM, CONN_1)  # keepalive finally notices the old socket

    registry.check(ROOM, CONN_2, ORIGIN_A)
    assert registry._holders[(ROOM, ORIGIN_A)] == CONN_2


def test_the_loser_cannot_move_to_another_origin(registry):
    registry.check(ROOM, CONN_1, ORIGIN_A)
    registry.check(ROOM, CONN_2, ORIGIN_A)

    with pytest.raises(ValueError):
        registry.check(ROOM, CONN_1, ORIGIN_B)


def test_the_loser_stays_locked_out_after_the_new_holder_leaves(registry):
    registry.check(ROOM, CONN_1, ORIGIN_A)
    registry.check(ROOM, CONN_2, ORIGIN_A)

    registry.release(ROOM, CONN_2)

    with pytest.raises(ValueError, match="newer connection"):
        registry.check(ROOM, CONN_1, ORIGIN_A)


def test_a_third_connection_can_take_over_again(registry):
    registry.check(ROOM, CONN_1, ORIGIN_A)
    registry.check(ROOM, CONN_2, ORIGIN_A)
    registry.check(ROOM, CONN_3, ORIGIN_A)

    with pytest.raises(ValueError, match="newer connection"):
        registry.check(ROOM, CONN_2, ORIGIN_A)


def test_takeover_is_the_known_gap_a_live_client_can_claim_an_origin(registry):
    # Documents D-063 rather than wanting it: a client that copies an origin off a relayed
    # operation is treated like a reconnect. Nothing can tell them apart until auth (#16 / #17).
    registry.check(ROOM, CONN_1, ORIGIN_A)  # the real client, still connected

    registry.check(ROOM, CONN_2, ORIGIN_A)  # accepted

    with pytest.raises(ValueError):
        registry.check(ROOM, CONN_1, ORIGIN_A)  # and the real client is now locked out
