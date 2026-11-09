"""Who may send as which `origin` (protocol rule 4, #10). The schema and size checks are in
operations.py; this is the part that needs to know about connections, but not about sockets.

Since #17 an origin belongs to a user: the first user to send as it owns it, and no other user
can send as it again (D-063 closed). The owner is kept in the database (OriginOwner), so a
restart doesn't free it; the relay looks it up there the first time it sees an origin and tells
this registry with `set_owner`. Within one user, the old rules still hold: the newest connection
to claim an origin holds it, which is how the add-on's reconnect takes it back.
"""

import logging

logger = logging.getLogger(__name__)


class OriginRegistry:
    """Which user owns which origin, and which connection holds it, per room.

    The first valid message on a connection pins that connection to its origin for good. An
    origin has one holder per room at a time, and the newest connection to claim it wins, if
    it's the owner's: the add-on reuses its origin when it reconnects, and the server can't
    tell a dead socket from a live one until keepalive notices, up to ~40 s later (D-062). The
    connection that lost it stays pinned to that origin, so it can't claim it back or move to
    another. A different user can never claim it.

    One per app (`app.state.origins`): user ids only mean something within one database.
    """

    def __init__(self) -> None:
        self._owners: dict[str, int] = {}  # origin -> user id, for every room
        self._pins: dict[tuple[str, int], str] = {}  # (room, connection) -> origin
        self._holders: dict[tuple[str, str], int] = {}  # (room, origin) -> connection

    def owner(self, origin: str) -> int | None:
        return self._owners.get(origin)

    def set_owner(self, origin: str, user_id: int) -> None:
        """Record the owner the database has for `origin`."""
        self._owners[origin] = user_id

    def check(self, room_id: str, conn_key: int, origin: str, user_id: int) -> None:
        """Allow a message claiming `origin` on this connection, signed in as `user_id`, or
        raise ValueError. An origin with no owner yet becomes `user_id`'s."""
        if self._owners.setdefault(origin, user_id) != user_id:
            logger.warning("origin claimed by another user room=%s origin=%s", room_id, origin)
            raise ValueError(f"origin {origin} belongs to another user")
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
        dead after a takeover doesn't free the origin, since the newer connection holds it.
        The origin's owner is kept: it's still theirs."""
        origin = self._pins.pop((room_id, conn_key), None)
        if origin is not None and self._holders.get((room_id, origin)) == conn_key:
            del self._holders[(room_id, origin)]
