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

Catch-up (#20): on every connection the server first sends the room's state as ordinary `ops`
messages, then `{"type": "synced", "seq": N}`. `ops` go to `on_message` as usual. The first
`synced` of a Join also calls `on_synced` with every object ID those catch-up messages
mentioned, which is how detect knows which local objects the room hasn't seen (D-085). Each
inbox entry carries its socket's generation, so a `synced` left over from a dead socket can't
mark the next one as caught up.

Sign-in (#16, #17): the token goes in an `Authorization: Bearer` header, never the URL. If the
server closes with 4401 (no or bad token) or 4403 (no access to the room), retrying with the same
token can only fail the same way, so the connection stops instead of reconnecting, with status
"refused" and the code in `refusal()`.
"""

import json
import queue
import re
import struct
import threading
import time
from collections import deque
from collections.abc import Callable

import bpy

from . import timing
from .log import log
from .vendor import websocket as _ws

DRAIN_INTERVAL = 0.02  # 20 ms
RECONNECT_BACKOFF = (0.5, 1, 2, 4)  # seconds; every 8 s after that
RECONNECT_STEADY = 8
OUTBOX_LIMIT = 1000

CLOSE_UNAUTHENTICATED = 4401  # sign in (again) first
CLOSE_FORBIDDEN = 4403  # not a member of the room, or it doesn't exist
_REFUSALS = (CLOSE_UNAUTHENTICATED, CLOSE_FORBIDDEN)

# Same pattern the server enforces (docs/protocol.md, #11); checked here too so a typo'd
# room id fails immediately instead of after a network round trip.
_ROOM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class _Connection:
    """One `connect()` call's worth of state: the outbox/inbox queues and the writer
    thread that owns the socket, reconnecting as needed until `stop()` is called."""

    def __init__(
        self,
        url: str,
        on_message: Callable[[dict], None],
        on_synced: Callable[[set[str]], None] | None = None,
        token: str = "",
    ) -> None:
        self.url = url
        self.on_message = on_message
        self.on_synced = on_synced
        self._header = [f"Authorization: Bearer {token}"] if token else []
        self.status = "connecting"
        self.refused: tuple[int, str] | None = None  # set by the reader on a 4401 / 4403 close
        self.inbox: queue.Queue[tuple[int, str]] = queue.Queue()
        # `generation` is bumped by the writer thread for each new socket; the rest is only
        # touched on the main thread, in drain().
        self.generation = 0
        self.synced_generation = -1  # the socket generation whose `synced` has arrived
        self.synced_seq: int | None = None
        self.joined = False  # whether this Join has had its first `synced`
        self.catch_up_ids: set[str] = set()
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
                sock.connect(self.url, header=self._header)
            except Exception as exc:  # noqa: BLE001 - any failure here just means retry
                log("client: connect failed", exc)
                self.status = "reconnecting"
                self._wait_backoff(attempt)
                attempt += 1
                continue

            with self._socket_lock:
                self._socket = sock
            self.generation += 1
            self.status = "connected"
            attempt = 0

            dead = threading.Event()
            reader = threading.Thread(
                target=self._run_reader, args=(sock, dead, self.generation), daemon=True
            )
            reader.start()
            self._run_send_loop(sock, dead)

            dead.set()
            reader.join(timeout=2)
            with self._socket_lock:
                self._socket = None
            if self.refused is not None:
                code, reason = self.refused
                log(f"client: the server refused the connection ({code} {reason}); not retrying")
                self.status = "refused"
                return
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
            timing.mark("dequeued", text)
            try:
                sock.send(text)
                timing.mark("sent", text)
            except Exception as exc:  # noqa: BLE001 - any send failure means reconnect
                log("client: send failed", exc)
                with self._outbox_lock:
                    self._outbox.appendleft(text)  # retry it on the next connection
                dead.set()
                return

    def _run_reader(self, sock: "_ws.WebSocket", dead: threading.Event, generation: int) -> None:
        while not dead.is_set():
            try:
                # recv_data rather than recv: recv turns a close frame into "", losing its code.
                opcode, data = sock.recv_data()
            except Exception as exc:  # noqa: BLE001 - any recv failure means reconnect
                log("client: recv failed", exc)
                dead.set()
                return
            if opcode == _ws.ABNF.OPCODE_CLOSE:
                self._note_close(data)
                dead.set()
                return
            text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
            if text == "":  # what a socket closed from our side gives
                dead.set()
                return
            timing.mark("received", text)
            self.inbox.put((generation, text))

    def _note_close(self, data: bytes) -> None:
        """Remember a 4401 / 4403 close, so the writer stops instead of reconnecting."""
        if len(data) < 2:
            return
        code = struct.unpack("!H", data[:2])[0]
        if code in _REFUSALS:
            self.refused = (code, data[2:].decode("utf-8", "replace"))

    def _wait_backoff(self, attempt: int) -> None:
        delay = RECONNECT_BACKOFF[attempt] if attempt < len(RECONNECT_BACKOFF) else RECONNECT_STEADY
        self._stopping.wait(delay)  # returns early if stop() is called mid-backoff


_conn: _Connection | None = None


def connect(
    server_url: str,
    room_id: str,
    on_message: Callable[[dict], None],
    on_synced: Callable[[set[str]], None] | None = None,
    token: str = "",
) -> None:
    """Connect to `<server_url>/ws/rooms/<room_id>`, signed in with `token`, and return
    immediately.

    `on_message` is called (on the main thread, from `drain()`) with each `ops` message, and
    `on_synced` once, at the first `synced`, with the IDs the room's catch-up mentioned.
    Replaces any existing connection. Raises `ValueError` for a `room_id` the server
    would refuse anyway, without touching the network.
    """
    global _conn
    if not _ROOM_ID_PATTERN.match(room_id):
        raise ValueError(f"invalid room id: {room_id!r}")
    if _conn is not None:
        _conn.stop()
    url = f"{server_url.rstrip('/')}/ws/rooms/{room_id}"
    _conn = _Connection(url, on_message, on_synced, token)
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=DRAIN_INTERVAL, persistent=True)


def send(message: dict) -> None:
    """Queue `message` to be sent as JSON. Never blocks; a no-op if not connected."""
    if _conn is not None:
        text = json.dumps(message)
        timing.mark("queued", message.get("ops", []))  # before it can reach the writer thread
        _conn.send(text)


def disconnect() -> None:
    """Close the connection and stop both threads and the timer. Safe to call anytime."""
    global _conn
    if _conn is not None:
        _conn.stop()
        _conn = None
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)


def status() -> str:
    """`"disconnected"`, `"connecting"`, `"connected"`, `"reconnecting"`, or `"refused"`: the
    server closed with 4401 or 4403, and the client has stopped (see `refusal()`)."""
    return _conn.status if _conn is not None else "disconnected"


def refusal() -> tuple[int, str] | None:
    """The close code and reason the server refused the connection with, if it did."""
    return _conn.refused if _conn is not None else None


def synced() -> bool:
    """Whether the current socket has received the room's catch-up (#20). False while
    connecting or reconnecting, and between connecting and the server's `synced`."""
    conn = _conn
    return (
        conn is not None
        and conn.status == "connected"
        and conn.synced_generation == conn.generation
    )


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
            generation, raw = conn.inbox.get_nowait()
        except queue.Empty:
            return
        timing.mark("drained", raw)
        _handle_message(conn, generation, raw)


def _note_catch_up_ids(conn: _Connection, message: dict) -> None:
    ops = message.get("ops")
    if not isinstance(ops, list):
        return
    for op in ops:
        if isinstance(op, dict) and isinstance(op.get("object"), str):
            conn.catch_up_ids.add(op["object"])


def _handle_synced(conn: _Connection, generation: int, message: dict) -> None:
    if generation != conn.generation:
        return  # from a socket that has since died
    conn.synced_generation = generation
    conn.synced_seq = message.get("seq")
    log("client: in sync with the room at seq", conn.synced_seq)
    if conn.joined:
        return  # a reconnect: edits made meanwhile are already in the outbox
    conn.joined = True
    known, conn.catch_up_ids = conn.catch_up_ids, set()
    if conn.on_synced is not None:
        conn.on_synced(known)


def _handle_message(conn: _Connection, generation: int, raw: str) -> None:
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
        if not conn.joined:
            _note_catch_up_ids(conn, message)
        conn.on_message(message)
        return
    if message_type == "synced":
        _handle_synced(conn, generation, message)
        return
    log("client: ignoring unknown message type", message_type)
