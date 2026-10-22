"""WebSocket connection to the relay server (#11, #12).

Two background daemon threads do all the networking: a reader (blocking `recv()` into
an inbox queue) and a writer (an outbox queue into `send()`), which together also own
the connect / reconnect lifecycle. Neither thread ever touches `bpy` — only the main
thread may. `drain()` is the only point where a received message reaches Blender: a
plain function, run by a `bpy.app.timers` tick on the main thread every ~20 ms.

Verified against the real relay from Blender 5.2's Python (10/21): a send from the main
thread arrives at another client's background reader; sending still works while the same
connection's reader is blocked in `recv()`; `close()` from the main thread stops the
reader within ~1 ms; a server that isn't running raises `ConnectionRefusedError`; and
after `close()`, `recv()` returns `""` rather than raising, so `""` means disconnected.
"""

import json
import queue
import re
import threading
import time
from collections import deque
from collections.abc import Callable

import bpy

from .log import log
from .vendor import websocket as _ws

DRAIN_INTERVAL = 0.02  # 20 ms
RECONNECT_BACKOFF = (0.5, 1, 2, 4)  # seconds; every 8 s after that
RECONNECT_STEADY = 8
OUTBOX_LIMIT = 1000

# Same pattern the server enforces (docs/protocol.md, #11); checked here too so a typo'd
# room id fails immediately instead of after a network round trip.
_ROOM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class _Connection:
    """One `connect()` call's worth of state: the outbox/inbox queues and the writer
    thread that owns the socket, reconnecting as needed until `stop()` is called."""

    def __init__(self, url: str, on_message: Callable[[dict], None]) -> None:
        self.url = url
        self.on_message = on_message
        self.status = "connecting"
        self.inbox: queue.Queue[str] = queue.Queue()
        self._outbox: deque[str] = deque(maxlen=OUTBOX_LIMIT)
        self._outbox_lock = threading.Lock()
        self._stopping = threading.Event()
        self._socket: _ws.WebSocket | None = None
        self._socket_lock = threading.Lock()
        self._writer = threading.Thread(target=self._run_writer, daemon=True)
        self._writer.start()

    def send(self, text: str) -> None:
        with self._outbox_lock:
            if len(self._outbox) == self._outbox.maxlen:
                log("client: outbox full (1000), dropping the oldest queued message")
            self._outbox.append(text)

    def stop(self) -> None:
        self._stopping.set()
        with self._socket_lock:
            sock = self._socket
        if sock is not None:
            try:
                sock.close()
            except Exception as exc:  # noqa: BLE001 - closing must not raise either way
                log("client: close raised while disconnecting", exc)
        self._writer.join(timeout=2)

    def _run_writer(self) -> None:
        attempt = 0
        while not self._stopping.is_set():
            try:
                sock = _ws.WebSocket()
                sock.connect(self.url)
            except Exception as exc:  # noqa: BLE001 - any failure here just means retry
                log("client: connect failed", exc)
                self.status = "reconnecting"
                self._wait_backoff(attempt)
                attempt += 1
                continue

            with self._socket_lock:
                self._socket = sock
            self.status = "connected"
            attempt = 0

            dead = threading.Event()
            reader = threading.Thread(target=self._run_reader, args=(sock, dead), daemon=True)
            reader.start()
            self._run_send_loop(sock, dead)

            dead.set()
            reader.join(timeout=2)
            with self._socket_lock:
                self._socket = None
            if not self._stopping.is_set():
                self.status = "reconnecting"

        self.status = "disconnected"

    def _run_send_loop(self, sock: "_ws.WebSocket", dead: threading.Event) -> None:
        """Send whatever's queued until the connection dies or `stop()` is called."""
        while not self._stopping.is_set() and not dead.is_set():
            with self._outbox_lock:
                text = self._outbox.popleft() if self._outbox else None
            if text is None:
                time.sleep(DRAIN_INTERVAL)
                continue
            try:
                sock.send(text)
            except Exception as exc:  # noqa: BLE001 - any send failure means reconnect
                log("client: send failed", exc)
                with self._outbox_lock:
                    self._outbox.appendleft(text)  # retry it on the next connection
                dead.set()
                return

    def _run_reader(self, sock: "_ws.WebSocket", dead: threading.Event) -> None:
        while not dead.is_set():
            try:
                text = sock.recv()
            except Exception as exc:  # noqa: BLE001 - any recv failure means reconnect
                log("client: recv failed", exc)
                dead.set()
                return
            if text == "":  # the verified close() signal, not an exception
                dead.set()
                return
            self.inbox.put(text)

    def _wait_backoff(self, attempt: int) -> None:
        delay = RECONNECT_BACKOFF[attempt] if attempt < len(RECONNECT_BACKOFF) else RECONNECT_STEADY
        self._stopping.wait(delay)  # returns early if stop() is called mid-backoff


_conn: _Connection | None = None


def connect(server_url: str, room_id: str, on_message: Callable[[dict], None]) -> None:
    """Connect to `<server_url>/ws/rooms/<room_id>` and return immediately.

    `on_message` is called (on the main thread, from `drain()`) with each `ops` message.
    Replaces any existing connection. Raises `ValueError` for a `room_id` the server
    would refuse anyway, without touching the network.
    """
    global _conn
    if not _ROOM_ID_PATTERN.match(room_id):
        raise ValueError(f"invalid room id: {room_id!r}")
    if _conn is not None:
        _conn.stop()
    url = f"{server_url.rstrip('/')}/ws/rooms/{room_id}"
    _conn = _Connection(url, on_message)
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=DRAIN_INTERVAL, persistent=True)


def send(message: dict) -> None:
    """Queue `message` to be sent as JSON. Never blocks; a no-op if not connected."""
    if _conn is not None:
        _conn.send(json.dumps(message))


def disconnect() -> None:
    """Close the connection and stop both threads and the timer. Safe to call anytime."""
    global _conn
    if _conn is not None:
        _conn.stop()
        _conn = None
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)


def status() -> str:
    """`"disconnected"`, `"connecting"`, `"connected"` or `"reconnecting"`."""
    return _conn.status if _conn is not None else "disconnected"


def _tick() -> float:
    drain()
    return DRAIN_INTERVAL


def drain() -> None:
    """Parse and dispatch every message received since the last call.

    A plain function (not the timer callback itself), so headless tests can call it
    directly; `bpy.app.timers` don't run without Blender's own event loop.
    """
    if _conn is None:
        return
    conn = _conn
    while True:
        try:
            raw = conn.inbox.get_nowait()
        except queue.Empty:
            return
        _handle_message(conn.on_message, raw)


def _handle_message(on_message: Callable[[dict], None], raw: str) -> None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError as exc:
        log("client: invalid JSON from server", exc)
        return
    if not isinstance(message, dict):
        log("client: ignoring non-object message from server")
        return
    message_type = message.get("type")
    if message_type == "error":
        log("client: server rejected a message:", message.get("message"))
        return
    if message_type == "ops":
        on_message(message)
        return
    log("client: ignoring unknown message type", message_type)
