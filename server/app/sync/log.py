"""Per-room append-only operation log (#19). Snapshot compaction comes with #20.

Takes a session and plain values, with no FastAPI or WebSocket imports, so it can be tested
alone and #20's catch-up can reuse it.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Operation
from app.sync.operations import OpsMessage

MAX_SINCE_LIMIT = 1000


async def append(session: AsyncSession, room_id: str, message: OpsMessage) -> list[int]:
    """Save one row per operation, all or none, and return their `seq`s in list order.

    `payload` is the validated model re-serialized, never the client's raw text, so the log
    only holds what passed validation: the same rule as broadcasting.
    """
    received_at = datetime.now(UTC)
    rows = [
        Operation(
            room_id=room_id,
            lamport=op.lamport,
            origin=op.origin,
            kind=op.kind,
            object=op.object,
            payload=op.model_dump_json(),
            received_at=received_at,
        )
        for op in message.ops
    ]
    try:
        session.add_all(rows)
        await session.flush()  # assigns each row's seq
        seqs = [row.seq for row in rows]
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return seqs


async def since(
    session: AsyncSession, room_id: str, after_seq: int = 0, limit: int = MAX_SINCE_LIMIT
) -> list[Operation]:
    """A room's operations with `seq` above `after_seq`, oldest first, at most `limit` of them.

    `limit` is clamped to 0..MAX_SINCE_LIMIT, since SQLite reads a negative LIMIT as "no limit".
    To page through a long log, pass the last row's `seq` as the next `after_seq`.
    """
    result = await session.scalars(
        select(Operation)
        .where(Operation.room_id == room_id, Operation.seq > after_seq)
        .order_by(Operation.seq)
        .limit(max(0, min(limit, MAX_SINCE_LIMIT)))
    )
    return list(result)
