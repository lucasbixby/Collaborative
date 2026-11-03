"""Who may send as which `origin` (protocol rule 4, #10). The schema and size checks are in
operations.py; this is the part that needs to know about connections, but not about sockets.

An origin can't be proven yet: it's a UUID every client in the room has seen on relayed
operations, and nothing ties it to a user until auth exists (#16 / #17). So this stops
mistakes and casual spoofing, not a determined client (D-063).
"""

import logging

logger = logging.getLogger(__name__)


class OriginRegistry:
    """Which connection holds which origin, per room.

    The first valid message on a connection pins that connection to its origin for good. An
    origin has one holder per room at a time, and the newest connection to claim it wins: the
    add-on reuses its origin when it reconnects, and the server can't tell a dead socket from
    a live one until keepalive notices, up to ~40 s later (D-062). The connection that lost it
    stays pinned to that origin, so it can't claim it back or move to another.
    """

    def __init__(self) -> None:
        self._pins: dict[tuple[str, int], str] = {}  # (room, connection) -> origin
        self._holders: dict[tuple[str, str], int] = {}  # (room, origin) -> connection

    def check(self, room_id: str, conn_key: int, origin: str) -> None:
        """Allow a message claiming `origin` on this connection, or raise ValueError."""
        pinned = self._pins.get((room_id, conn_key))
        if pinned is None:
            self._pins[(room_id, conn_key)] = origin
            previous = self._holders.get((room_id, origin))
            self._holders[(room_id, origin)] = conn_key
            if previous is not None:
                logger.warning("origin takeover room=%s origin=%s", room_id, origin)
            return
        if pinned != origin:
            raise ValueError(f"this connection sends as origin {pinned}, not {origin}")
        if self._holders.get((room_id, origin)) != conn_key:
            raise ValueError(f"origin {origin} has moved to a newer connection")

    def release(self, room_id: str, conn_key: int) -> None:
        """Forget a closed connection. Safe if it never pinned anything. A stale socket found
        dead after a takeover doesn't free the origin, since the newer connection holds it."""
        origin = self._pins.pop((room_id, conn_key), None)
        if origin is not None and self._holders.get((room_id, origin)) == conn_key:
            del self._holders[(room_id, origin)]
