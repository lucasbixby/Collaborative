"""Tests for the WebSocket client (#12), against conftest.py's fake relay server."""

import json
import threading

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
