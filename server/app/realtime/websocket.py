"""WebSocket relay endpoint: one connection per client, one room per project (#11).

A room's connections exist only while at least one client is in it, but its operations are
kept in the log (#19).

Sign-in (#16): the token comes in the `Authorization: Bearer` header, never the URL, which
uvicorn's access log records. The socket is accepted first and then closed with 4401 if the
token is missing or bad, so a client sees the code and the reason rather than a failed
handshake (docs/protocol.md).

On connect, catch-up (#20): under the room's lock, the socket joins the room, gets the room's
current state as ordinary `ops` messages (app.sync.state), then `{"type": "synced", "seq": N}`.
The same lock is held around "append -> broadcast" below, so a live op can't reach a client
before its catch-up, or land between reading the state and joining (D-083). A first join, a
late join and a reconnect all take this path, so a client never has to ask (D-084).

The handler never awaits the database directly: queries run through `tasks.shielded`, so a
client leaving mid-query (which cancels this handler) can't leave a connection half-closed, and
snapshots run as background tasks the app waits for at shutdown (app.realtime.tasks, D-088).

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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.tokens import InvalidToken, bearer_token, verify_token
from app.db.models import User
from app.sync import log as operation_log
from app.sync import state as room_state
from app.sync import timing
from app.sync.conflicts import RoomState
from app.sync.operations import parse_message, serialize_message
from app.sync.validation import OriginRegistry

from .connections import ConnectionManager

logger = logging.getLogger(__name__)
router = APIRouter()
manager = ConnectionManager()
origins = OriginRegistry()

ROOM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Close codes in the 4000s are the application's own (RFC 6455 7.4.2). Like HTTP's 401: the
# client should sign in (again) before retrying, not reconnect with the same token.
CLOSE_UNAUTHENTICATED = 4401


async def _send_error(websocket: WebSocket, reason: str) -> None:
    await websocket.send_text(json.dumps({"v": 1, "type": "error", "message": reason}))


def _room_lock(websocket: WebSocket, room_id: str) -> asyncio.Lock:
    """The room's lock. Kept on `app.state` (set up in the app's lifespan) rather than in this
    module, because a lock belongs to one event loop and each app (each test) runs its own."""
    return websocket.app.state.room_locks[room_id]


async def _read_for_catch_up(app, room_id: str) -> tuple[RoomState, int]:
    """The room's state, seeding its snapshot count the first time this process sees it."""
    async with app.state.sessions() as session:
        current, last_seq = await room_state.load_state(session, room_id)
        if not app.state.snapshots.seeded(room_id):
            pending = await room_state.ops_since_snapshot(session, room_id)
            app.state.snapshots.seed(room_id, pending)
    return current, last_seq


async def _append(app, room_id: str, message) -> list[int]:
    async with app.state.sessions() as session:
        return await operation_log.append(session, room_id, message)


async def _find_user(app, token: str) -> User | None:
    async with app.state.sessions() as session:
        try:
            return await verify_token(session, token)
        except InvalidToken:
            return None


async def _authenticate(websocket: WebSocket) -> User | None:
    """The signed-in user, or None after closing the socket with 4401."""
    token = bearer_token(websocket.headers.get("authorization"))
    user = None
    if token is not None:
        user = await websocket.app.state.tasks.shielded(_find_user(websocket.app, token))
    if user is None:
        reason = "sign in first" if token is None else "invalid or expired token; sign in again"
        logger.info("refused: %s", reason)
        await websocket.close(code=CLOSE_UNAUTHENTICATED, reason=reason)
    return user


async def _join_and_catch_up(websocket: WebSocket, room_id: str) -> int:
    """Join the room, then send its state and `synced`, all under the room's lock. A client
    that leaves part way through just ends this early: the read is shielded, and the lock and
    the room are released on the way out."""
    app = websocket.app
    async with _room_lock(websocket, room_id):
        count = manager.join(room_id, websocket)
        current, last_seq = await app.state.tasks.shielded(_read_for_catch_up(app, room_id))
        messages = room_state.catch_up_messages(current)
        for text in messages:
            await websocket.send_text(text)
        await websocket.send_text(room_state.encode({"v": 1, "type": "synced", "seq": last_seq}))
    logger.info("catch-up room=%s messages=%d seq=%d", room_id, len(messages), last_seq)
    return count


@router.websocket("/ws/rooms/{room_id}")
async def room_socket(websocket: WebSocket, room_id: str) -> None:
    if not ROOM_ID_PATTERN.match(room_id):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    with websocket.app.state.tasks.handler(websocket):
        user = await _authenticate(websocket)
        if user is not None:
            await _relay(websocket, room_id)


async def _relay(websocket: WebSocket, room_id: str) -> None:
    app = websocket.app
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
                    seqs = await app.state.tasks.shielded(_append(app, room_id, message))
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
                app.state.snapshots.appended(room_id, len(seqs))
    except WebSocketDisconnect:
        pass
    finally:
        origins.release(room_id, id(websocket))
        count = manager.leave(room_id, websocket)
        logger.info("disconnect room=%s clients=%d", room_id, count)
