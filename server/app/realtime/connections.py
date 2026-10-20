"""Tracks which sockets are in which room and broadcasts operations to them.

Knows nothing about operation contents; ordering and validation live in app.sync. One
instance per server process, held in memory: rooms don't survive a restart (#19).
"""

from fastapi import WebSocket


class ConnectionManager:
    """Room membership (room_id -> sockets) and broadcast."""

    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = {}

    def join(self, room_id: str, socket: WebSocket) -> int:
        """Add `socket` to `room_id`, creating it if needed. Returns the new client count."""
        room = self._rooms.setdefault(room_id, set())
        room.add(socket)
        return len(room)

    def leave(self, room_id: str, socket: WebSocket) -> int:
        """Remove `socket` from `room_id`, deleting the room once it's empty.

        Returns the room's remaining client count (0 if the room no longer exists).
        """
        room = self._rooms.get(room_id)
        if room is None:
            return 0
        room.discard(socket)
        if room:
            return len(room)
        del self._rooms[room_id]
        return 0

    async def broadcast(self, room_id: str, text: str, *, exclude: WebSocket) -> None:
        """Send `text` to every socket in `room_id` except `exclude`.

        Iterates a copy of the room's sockets, since a failed send mutates it. The failed
        socket is dropped here; its own `receive` loop will separately notice the
        disconnect and call `leave`.
        """
        room = self._rooms.get(room_id)
        if room is None:
            return
        for socket in list(room):
            if socket is exclude:
                continue
            try:
                await socket.send_text(text)
            except Exception:  # noqa: BLE001 - any failed send means this client is gone
                room.discard(socket)
