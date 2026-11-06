"""WebSocket relay endpoint: one connection per client, one room per project (#11).

Minimal version for the prototype (10/24): no accounts (TODO #16 / #17), no ordering
beyond arrival order (#8 / #9). A room's connections exist only while at least one client
is in it, but its operations are kept in the log (#19).

On connect, catch-up (#20): under the room's lock, the socket joins the room, gets the room's
current state as ordinary `ops` messages (app.sync.state), then `{"type": "synced", "seq": N}`.
The same lock is held around "append -> broadcast" below, so a live op can't reach a client
before its catch-up, or land between reading the state and joining (D-083). A first join, a
late join and a reconnect all take this path, so a client never has to ask (D-084).

Flow for each incoming message:
  1. `parse_message` (app.sync.operations) checks size and schema, then `origins`
     (app.sync.validation) checks this connection may send as that origin (#10).
  2. Valid: append it to the operation log (app.sync.log), so nothing is ever broadcast that
     isn't in the log.
  3. Saved: broadcast `serialize_message(parsed)` to every other client in the room, never
     back to the sender, which has already applied its own change. The re-serialized
     message is forwarded rather than the raw text, so only validated content leaves the
     server (docs/protocol.md).
  4. Invalid or not saved: reply to the sender only with an `error` message and keep the
     connection open. One bad batch shouldn't disconnect a client.
"""

import asyncio
import json
import logging
import re
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.sync import log as operation_log
from app.sync import state as room_state
from app.sync import timing
from app.sync.operations import parse_message, serialize_message
from app.sync.validation import OriginRegistry

from .connections import ConnectionManager

logger = logging.getLogger(__name__)
router = APIRouter()
manager = ConnectionManager()
origins = OriginRegistry()

ROOM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


async def _send_error(websocket: WebSocket, reason: str) -> None:
    await websocket.send_text(json.dumps({"v": 1, "type": "error", "message": reason}))


def _room_lock(websocket: WebSocket, room_id: str) -> asyncio.Lock:
    """The room's lock. Kept on `app.state` rather than in this module, because a lock belongs
    to one event loop and each app (each test) runs its own. Never removed, so this grows by
    one small lock per room the process has seen."""
    state = websocket.app.state
    if not hasattr(state, "room_locks"):
        state.room_locks = defaultdict(asyncio.Lock)
    return state.room_locks[room_id]


async def _join_and_catch_up(websocket: WebSocket, room_id: str) -> int:
    """Join the room, then send its state and `synced`, all under the room's lock."""
    async with _room_lock(websocket, room_id):
        count = manager.join(room_id, websocket)
        async with websocket.app.state.sessions() as session:
            current, last_seq = await room_state.load_state(session, room_id)
        messages = room_state.catch_up_messages(current)
        for text in messages:
            await websocket.send_text(text)
        await websocket.send_text(room_state.encode({"v": 1, "type": "synced", "seq": last_seq}))
    logger.info("catch-up room=%s messages=%d seq=%d", room_id, len(messages), last_seq)
    return count


async def _snapshot_if_due(websocket: WebSocket, room_id: str) -> None:
    """A snapshot is only a cache over the log, so a failure here is logged and nothing else:
    the op is already saved and relayed."""
    try:
        async with websocket.app.state.sessions() as session:
            snapshot = await room_state.maybe_snapshot(session, room_id)
    except Exception:
        logger.exception("snapshot failed room=%s", room_id)
        return
    if snapshot is not None:
        logger.info("snapshot room=%s seq=%d", room_id, snapshot.seq)


@router.websocket("/ws/rooms/{room_id}")
async def room_socket(websocket: WebSocket, room_id: str) -> None:
    if not ROOM_ID_PATTERN.match(room_id):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    try:
        count = await _join_and_catch_up(websocket, room_id)
        logger.info("connect room=%s clients=%d", room_id, count)
        while True:
            raw = await websocket.receive_text()
            received_at = timing.now()
            try:
                message = parse_message(raw)
                origins.check(room_id, id(websocket), message.origin)
            except ValueError as exc:
                logger.info("reject room=%s reason=%s", room_id, exc)
                await _send_error(websocket, str(exc))
                continue
            timing.mark("server_received", message, received_at)
            timing.mark("server_parsed", message)
            async with _room_lock(websocket, room_id):
                try:
                    async with websocket.app.state.sessions() as session:
                        await operation_log.append(session, room_id, message)
                except Exception:
                    logger.exception("append failed room=%s", room_id)
                    # Generic on purpose: database details stay in the server's log.
                    await _send_error(
                        websocket, "the server couldn't save this message; not relayed"
                    )
                    continue
                timing.mark("server_persisted", message)
                await manager.broadcast(room_id, serialize_message(message), exclude=websocket)
                timing.mark("server_broadcast", message)
                await _snapshot_if_due(websocket, room_id)
    except WebSocketDisconnect:
        pass
    finally:
        origins.release(room_id, id(websocket))
        count = manager.leave(room_id, websocket)
        logger.info("disconnect room=%s clients=%d", room_id, count)
