"""REST: a room's current state and its operation history (#20).

The socket already sends a joining client the room's state (app.realtime.websocket), so these
are for anything else that wants to look: the web UI, scripts, debugging. Both read through
the same functions the socket uses. Both are for the room's members, viewers included (#17).
"""

import json
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.auth.membership import Member
from app.sync import log
from app.sync.state import load_state

router = APIRouter()


@router.get("/{room_id}/snapshot")
async def get_snapshot(request: Request, member: Member) -> dict:
    """The room's current state as ops (latest snapshot + log after it), and the last `seq`
    included."""
    room_id = member.room.id
    async with request.app.state.sessions() as session:
        state, seq = await load_state(session, room_id)
    return {"room_id": room_id, "seq": seq, "ops": state.to_ops()}


@router.get("/{room_id}/operations")
async def get_operations(
    request: Request,
    member: Member,
    since: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=log.MAX_SINCE_LIMIT)] = log.MAX_SINCE_LIMIT,
) -> dict:
    """Log rows with `seq` above `since`, oldest first. The cursor is `seq`, the server's
    arrival order, not a Lamport time: pass the last row's `seq` to get the next page."""
    room_id = member.room.id
    async with request.app.state.sessions() as session:
        rows = await log.since(session, room_id, since, limit)
    return {
        "room_id": room_id,
        "operations": [
            {
                "seq": row.seq,
                "received_at": row.received_at.isoformat(),
                "op": json.loads(row.payload),
            }
            for row in rows
        ],
    }
