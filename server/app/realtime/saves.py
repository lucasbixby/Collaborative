"""Pending save requests: a guest saved in Blender and is waiting for the host's answer.

In memory, one per (room, user). A request the host never answers expires, so an old pop-up
can't trigger a save long after anyone wanted it."""

import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

EXPIRES_AFTER = 600  # seconds


@dataclass
class SaveRequest:
    room_id: str
    user_id: int
    username: str
    id: str = field(default_factory=lambda: secrets.token_urlsafe(9))
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    _made: float = field(default_factory=time.monotonic)


class SaveRequests:
    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._by_room: dict[str, dict[int, SaveRequest]] = {}

    def add(self, room_id: str, user_id: int, username: str) -> SaveRequest:
        """Record the user's request, replacing an earlier one from them that's still pending."""
        request = SaveRequest(room_id, user_id, username, _made=self._clock())
        self._by_room.setdefault(room_id, {})[user_id] = request
        return request

    def pending(self, room_id: str) -> list[SaveRequest]:
        requests = self._by_room.get(room_id)
        if not requests:
            return []
        cutoff = self._clock() - EXPIRES_AFTER
        for user_id in [uid for uid, request in requests.items() if request._made <= cutoff]:
            del requests[user_id]
        if not requests:
            del self._by_room[room_id]
        return sorted(requests.values(), key=lambda request: request.requested_at)

    def take(self, room_id: str, request_id: str) -> SaveRequest | None:
        """Remove and return a pending request, or None if it's unknown or expired."""
        for request in self.pending(room_id):
            if secrets.compare_digest(request.id, request_id):
                del self._by_room[room_id][request.user_id]
                return request
        return None

    def drop_user(self, room_id: str, user_id: int) -> None:
        self._by_room.get(room_id, {}).pop(user_id, None)

    def drop_room(self, room_id: str) -> None:
        self._by_room.pop(room_id, None)
