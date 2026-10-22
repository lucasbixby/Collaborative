"""Tests for the WebSocket client (#12), against a small fake relay server.

Not the real relay (#11 has its own tests against that) — just enough of a WebSocket
server, run on a background thread with its own event loop, to drive client.py's own
behaviour: connecting, sending, receiving, and reconnecting.
"""

import asyncio
import json
import threading
import time

import pytest
import websockets

from collaborative_blender import client


def _wait_until(predicate, timeout=2.0, interval=0.01) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s")


class FakeRelay:
    """A minimal WebSocket server: records what it receives, and lets a test push a
    message to the connected client, or stop (and later restart) the server, on demand.
    """

    def __init__(self) -> None:
        self.received: list[str] = []
        self.port: int | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: websockets.Server | None = None
        self._sockets: list = []
        self._thread: threading.Thread | None = None
        self._stopped = False

    def start(self, port: int = 0) -> None:
        ready = threading.Event()

        def _run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop

            async def _main() -> None:
                # A short close_timeout: otherwise stop() waits (by default) up to 10 s
                # for a close-handshake ack the test's client never sends.
                self._server = await websockets.serve(
                    self._handler, "localhost", port, close_timeout=0.2
                )
                self.port = next(iter(self._server.sockets)).getsockname()[1]
                ready.set()
                await self._server.wait_closed()

            loop.run_until_complete(_main())

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        ready.wait(timeout=5)

    async def _handler(self, websocket) -> None:
        self._sockets.append(websocket)
        try:
            async for message in websocket:
                self.received.append(message)
        finally:
            if websocket in self._sockets:
                self._sockets.remove(websocket)

    def send_to_client(self, text: str) -> None:
        for socket in list(self._sockets):
            asyncio.run_coroutine_threadsafe(socket.send(text), self._loop).result(timeout=5)

    def stop(self) -> None:
        """Idempotent: a test may stop the relay itself, so the fixture's own teardown
        must not fail when it calls this a second time."""
        if self._stopped:
            return
        self._stopped = True
        if self._server is not None:

            async def _close() -> None:
                self._server.close()
                await self._server.wait_closed()

            asyncio.run_coroutine_threadsafe(_close(), self._loop).result(timeout=5)
        if self._thread is not None:
            self._thread.join(timeout=5)


@pytest.fixture
def relay():
    server = FakeRelay()
    server.start()
    yield server
    server.stop()


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
