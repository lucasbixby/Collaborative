"""A room's current state: the latest snapshot plus the log after it (#20).

`load_state` is the one way to read it, used by the socket's catch-up and by REST.
`maybe_snapshot` runs after each append and writes a new snapshot once the log has grown
`settings.snapshot_every` operations past the last one (D-082). Log rows are never deleted:
the history is a success criterion, so compaction is a follow-up.

`catch_up_messages` turns a state into `ops` messages that obey the same rules as any
client's: one `create` per message, one origin per message, each at most the size limit.
"""

import json
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Operation, Snapshot
from app.sync import log
from app.sync.conflicts import RoomState


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


async def maybe_snapshot(session: AsyncSession, room_id: str) -> Snapshot | None:
    """Write a snapshot if the log has grown `snapshot_every` ops past the latest one."""
    snapshot = await latest_snapshot(session, room_id)
    after = snapshot.seq if snapshot else 0
    pending = await session.scalar(
        select(func.count())
        .select_from(Operation)
        .where(Operation.room_id == room_id, Operation.seq > after)
    )
    if pending < settings.snapshot_every:
        return None
    state, last_seq = await load_state(session, room_id)
    new = Snapshot(
        room_id=room_id, seq=last_seq, state=state.to_json(), created_at=datetime.now(UTC)
    )
    session.add(new)
    await session.commit()
    return new


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
