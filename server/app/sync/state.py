"""A room's current state: the latest snapshot plus the log after it (#20).

`load_state` is the one way to read it, used by the socket's catch-up and by REST.
`SnapshotScheduler` decides when to write a snapshot (every `settings.snapshot_every`
operations, D-082) by counting in memory, and writes it in a background task, so the relay
never touches the database for it per message (D-088). Log rows are never deleted: the history
is a success criterion, so compaction is a follow-up.

`catch_up_messages` turns a state into `ops` messages that obey the same rules as any
client's: one `create` per message, one origin per message, each at most the size limit.
"""

import json
import logging
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import Operation, Snapshot
from app.sync import log
from app.sync.conflicts import RoomState

logger = logging.getLogger(__name__)


def encode(message: dict) -> str:
    """Compact JSON, the same shape `serialize_message` produces for the relay."""
    return json.dumps(message, separators=(",", ":"), allow_nan=False)


async def latest_snapshot(session: AsyncSession, room_id: str) -> Snapshot | None:
    return await session.scalar(
        select(Snapshot).where(Snapshot.room_id == room_id).order_by(Snapshot.seq.desc()).limit(1)
    )


async def load_state(session: AsyncSession, room_id: str) -> tuple[RoomState, int]:
    """The room's state and the last `seq` it includes (0 for a room with no operations).

    Reads in one transaction, so with SQLite's WAL the snapshot and the log rows after it
    are one consistent view even while others append.
    """
    snapshot = await latest_snapshot(session, room_id)
    state = RoomState.from_json(snapshot.state) if snapshot else RoomState()
    last_seq = snapshot.seq if snapshot else 0
    while rows := await log.since(session, room_id, last_seq):
        state.apply_all(json.loads(row.payload) for row in rows)
        last_seq = rows[-1].seq
    return state, last_seq


async def ops_since_snapshot(session: AsyncSession, room_id: str) -> int:
    """How many of the room's log rows come after its latest snapshot."""
    snapshot = await latest_snapshot(session, room_id)
    return await session.scalar(
        select(func.count())
        .select_from(Operation)
        .where(Operation.room_id == room_id, Operation.seq > (snapshot.seq if snapshot else 0))
    )


async def write_snapshot(session: AsyncSession, room_id: str) -> Snapshot:
    """Fold the room's current state and save it as a new snapshot."""
    state, last_seq = await load_state(session, room_id)
    new = Snapshot(
        room_id=room_id, seq=last_seq, state=state.to_json(), created_at=datetime.now(UTC)
    )
    session.add(new)
    await session.commit()
    return new


class SnapshotScheduler:
    """Counts each room's appends since its last snapshot, in memory, and starts a snapshot
    task once the count reaches `settings.snapshot_every` (D-088).

    A room's count is seeded from the database once, by `seed`, which catch-up calls before
    the room's first append in this process. A room that was never seeded counts from 0, which
    only delays its next snapshot. At most one snapshot per room runs at a time. A snapshot that
    fails, or is cancelled at shutdown, is just skipped: it's a cache over the log (D-082).
    """

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        spawn: Callable[[Coroutine[Any, Any, Any]], Any],
    ) -> None:
        self._sessions = sessions
        self._spawn = spawn
        self._pending: dict[str, int] = {}
        self._running: set[str] = set()

    def seeded(self, room_id: str) -> bool:
        return room_id in self._pending

    def seed(self, room_id: str, pending: int) -> None:
        """Start counting from `pending`, the ops already logged since the latest snapshot."""
        self._pending.setdefault(room_id, pending)

    def appended(self, room_id: str, count: int) -> None:
        """Note `count` new ops for the room, starting a snapshot if one is due."""
        pending = self._pending.get(room_id, 0) + count
        if pending >= settings.snapshot_every and room_id not in self._running:
            pending = 0  # ops appended while it's written are counted towards the next one
            self._running.add(room_id)
            self._spawn(self._take(room_id))
        self._pending[room_id] = pending

    async def _take(self, room_id: str) -> None:
        try:
            async with self._sessions() as session:
                snapshot = await write_snapshot(session, room_id)
            logger.info("snapshot room=%s seq=%d", room_id, snapshot.seq)
        except Exception:
            logger.exception("snapshot failed room=%s", room_id)
        finally:
            self._running.discard(room_id)


def catch_up_messages(state: RoomState, max_bytes: int | None = None) -> list[str]:
    """The state as `ops` messages, in `to_ops` order: each `create` alone, then the `set`s
    and `delete`s batched per origin (protocol rule 4), each message at most `max_bytes`."""
    limit = settings.max_operation_bytes if max_bytes is None else max_bytes
    empty = len(encode({"v": 1, "type": "ops", "ops": []}))
    messages: list[str] = []
    batches: dict[str, tuple[list[str], int]] = {}  # origin -> (encoded ops, message size)

    def flush(origin: str) -> None:
        encoded, _size = batches.pop(origin)
        messages.append(f'{{"v":1,"type":"ops","ops":[{",".join(encoded)}]}}')

    for op in state.to_ops():
        text = encode(op)
        if op["kind"] == "create":
            # It arrived as a message of its own that fit, and this encoding is compact.
            messages.append(f'{{"v":1,"type":"ops","ops":[{text}]}}')
            continue
        origin = op["origin"]
        cost = len(text.encode("utf-8"))
        if origin in batches and batches[origin][1] + 1 + cost > limit:
            flush(origin)
        if origin in batches:
            encoded, size = batches[origin]
            encoded.append(text)
            batches[origin] = (encoded, size + 1 + cost)
        else:
            batches[origin] = ([text], empty + cost)
    for origin in list(batches):
        flush(origin)
    return messages
