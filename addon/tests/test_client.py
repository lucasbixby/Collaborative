"""Tests for the WebSocket client (#12), against conftest.py's fake relay server."""

import json
import threading
import time

import pytest
from conftest import FakeRelay
from conftest import wait_until as _wait_until

from collaborative_blender import client


@pytest.fixture(autouse=True)
def _disconnect_after_every_test():
    yield
    client.disconnect()


def test_status_goes_to_connected(relay):
    client.connect(f"ws://localhost:{relay.port}", "room-a", lambda message: None)

    _wait_until(lambda: client.status() == "connected")


def test_send_reaches_the_server_as_json(relay):
    client.connect(f"ws://localhost:{relay.port}", "room-a", lambda message: None)
    _wait_until(lambda: client.status() == "connected")

    client.send({"v": 1, "type": "ops", "ops": []})

    _wait_until(lambda: len(relay.received) == 1)
    assert json.loads(relay.received[0]) == {"v": 1, "type": "ops", "ops": []}


def test_server_message_reaches_on_message_via_drain_on_the_calling_thread(relay):
    received = []
    calling_thread = threading.current_thread()

    def on_message(message):
        received.append((message, threading.current_thread()))

    client.connect(f"ws://localhost:{relay.port}", "room-a", on_message)
    _wait_until(lambda: client.status() == "connected")

    relay.send_to_client(json.dumps({"v": 1, "type": "ops", "ops": []}))
    _wait_until(lambda: client._conn.inbox.qsize() > 0)  # arrived, not yet drained

    assert received == []  # drain() hasn't run yet, so on_message hasn't either
    client.drain()

    assert len(received) == 1
    message, thread = received[0]
    assert message == {"v": 1, "type": "ops", "ops": []}
    assert thread is calling_thread  # not the reader thread


def test_error_and_invalid_json_are_logged_not_passed_on(relay, capsys):
    received = []
    client.connect(f"ws://localhost:{relay.port}", "room-a", received.append)
    _wait_until(lambda: client.status() == "connected")

    relay.send_to_client("not valid json {")
    relay.send_to_client(json.dumps({"v": 1, "type": "error", "message": "bad batch"}))
    _wait_until(lambda: client._conn.inbox.qsize() >= 2)

    client.drain()

    assert received == []  # neither one reached on_message
    output = capsys.readouterr().out
    assert "invalid JSON" in output
    assert "bad batch" in output


def test_reconnect_after_server_restart_delivers_queued_messages(relay):
    client.connect(f"ws://localhost:{relay.port}", "room-a", lambda message: None)
    _wait_until(lambda: client.status() == "connected")
    port = relay.port

    relay.stop()
    _wait_until(lambda: client.status() == "reconnecting", timeout=5)

    client.send({"v": 1, "type": "ops", "ops": []})  # queued while disconnected

    restarted = FakeRelay()
    try:
        restarted.start(port=port)
        _wait_until(lambda: client.status() == "connected", timeout=10)
        _wait_until(lambda: len(restarted.received) == 1, timeout=5)
    finally:
        restarted.stop()

    assert json.loads(restarted.received[0]) == {"v": 1, "type": "ops", "ops": []}


def test_connecting_to_a_dead_server_does_not_raise_and_reports_reconnecting():
    client.connect("ws://localhost:1", "room-a", lambda message: None)  # nothing listening

    _wait_until(lambda: client.status() == "reconnecting", timeout=5)


def test_disconnect_leaves_no_client_threads_running(relay):
    before = {t.ident for t in threading.enumerate()}
    client.connect(f"ws://localhost:{relay.port}", "room-a", lambda message: None)
    _wait_until(lambda: client.status() == "connected")

    client.disconnect()

    after = {t.ident for t in threading.enumerate()}
    assert after - before == set()
    assert client.status() == "disconnected"


def test_invalid_room_id_is_refused():
    with pytest.raises(ValueError):
        client.connect("ws://localhost:9", "bad room!", lambda message: None)

    assert client.status() == "disconnected"


# -- Sign-in (#16, #17) -------------------------------------------------------------------


def test_the_token_is_sent_as_an_authorization_header(relay):
    client.connect(f"ws://localhost:{relay.port}", "room-a", lambda message: None, token="t0k")
    _wait_until(lambda: client.status() == "connected")

    assert relay.authorizations == ["Bearer t0k"]


def test_no_token_sends_no_authorization_header(relay):
    client.connect(f"ws://localhost:{relay.port}", "room-a", lambda message: None)
    _wait_until(lambda: client.status() == "connected")

    assert relay.authorizations == [None]


@pytest.mark.parametrize(
    ("code", "reason"), [(4401, "sign in first"), (4403, "no access to room-a")]
)
def test_a_refusal_stops_the_client_instead_of_reconnecting(relay, code, reason):
    relay.refuse_with = (code, reason)
    client.connect(f"ws://localhost:{relay.port}", "room-a", lambda message: None, token="t0k")

    _wait_until(lambda: client.status() == "refused")
    assert client.refusal() == (code, reason)
    # Longer than the first two backoff steps (0.5 s, 1 s): no second attempt was made.
    time.sleep(2)
    assert len(relay.authorizations) == 1
    assert not client._conn._writer.is_alive()


def test_an_ordinary_close_still_reconnects(relay):
    client.connect(f"ws://localhost:{relay.port}", "room-a", lambda message: None)
    _wait_until(lambda: client.status() == "connected")

    relay.drop_clients()

    _wait_until(lambda: len(relay.authorizations) == 2, timeout=5)
    _wait_until(lambda: client.status() == "connected")
    assert client.refusal() is None


def test_join_again_after_a_refusal_makes_a_fresh_attempt(relay):
    relay.refuse_with = (4401, "sign in first")
    client.connect(f"ws://localhost:{relay.port}", "room-a", lambda message: None)
    _wait_until(lambda: client.status() == "refused")

    relay.refuse_with = None
    client.connect(f"ws://localhost:{relay.port}", "room-a", lambda message: None, token="new")

    _wait_until(lambda: client.status() == "connected")
    assert relay.authorizations == [None, "Bearer new"]
    assert client.refusal() is None
