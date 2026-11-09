"""WebSocket relay endpoint: one connection per client, one room per project (#11).

A room's connections exist only while at least one client is in it, but its operations are
kept in the log (#19).

Access (#16, #17): the token comes in the `Authorization: Bearer` header, never the URL, which
uvicorn's access log records. The socket is accepted first, then closed before any catch-up with
4401 if the token is missing or bad, or 4403 if the room doesn't exist or the user isn't in it,
so a client sees the code and the reason rather than a failed handshake (docs/protocol.md). The
role is kept on the connection (`websocket.state.access`): a viewer gets the catch-up and every
live op, but its own `ops` get an `error` and go nowhere. `member_changed` applies a role
change or removal made over REST to open connections straight away.

On connect, catch-up (#20): under the room's lock, the socket joins the room, gets the room's
current state as ordinary `ops` messages (app.sync.state), then `{"type": "synced", "seq": N}`.
The same lock is held around "append -> broadcast" below, so a live op can't reach a client
before its catch-up, or land between reading the state and joining (D-083). A first join, a
late join and a reconnect all take this path, so a client never has to ask (D-084).

The handler never awaits the database directly: queries run through `tasks.shielded`, so a
client leaving mid-query (which cancels this handler) can't leave a connection half-closed, and
snapshots run as background tasks the app waits for at shutdown (app.realtime.tasks, D-088).

Flow for each incoming message:
  1. A viewer's message is refused unread. Otherwise `parse_message` (app.sync.operations)
     checks size and schema, then `origins` (app.sync.validation) checks this connection's
     user may send as that origin (#10, #17).
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
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth.membership import ROOM_ID_PATTERN, role_in
from app.auth.permissions import Role, can_join, can_send_operations
from app.auth.tokens import InvalidToken, bearer_token, verify_token
from app.db.models import OriginOwner
from app.sync import log as operation_log
from app.sync import state as room_state
from app.sync import timing
from app.sync.conflicts import RoomState
from app.sync.operations import parse_message, serialize_message

from .connections import ConnectionManager

logger = logging.getLogger(__name__)
router = APIRouter()
manager = ConnectionManager()

_ROOM_ID = re.compile(ROOM_ID_PATTERN)

# Close codes in the 4000s are the application's own (RFC 6455 7.4.2), named after HTTP's. The
# client should sign in, or be invited, before trying again: reconnecting can't help.
CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN = 4403

VIEWER_ERROR = "viewers can't edit"
SAVE_ERROR = "the server couldn't save this message; not relayed"


@dataclass
class Access:
    """Who a connection is signed in as, and their role in its room right now."""

    user_id: int
    username: str
    role: Role
    removed: bool = False  # set by member_changed, which has closed the socket


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


async def _look_up_access(app, room_id: str, token: str) -> tuple[bool, Access | None]:
    """(whether the token is good, the user's access to the room if they have any)."""
    async with app.state.sessions() as session:
        try:
            user = await verify_token(session, token)
        except InvalidToken:
            return False, None
        role = await role_in(session, room_id, user.id)
    return True, Access(user.id, user.username, role) if can_join(role) else None


async def _authorize(websocket: WebSocket, room_id: str) -> Access | None:
    """The connection's access to the room, or None after closing it with 4401 or 4403."""
    token = bearer_token(websocket.headers.get("authorization"))
    signed_in, access = False, None
    if token is not None:
        app = websocket.app
        signed_in, access = await app.state.tasks.shielded(_look_up_access(app, room_id, token))
    if access is not None:
        return access
    if token is None:
        code, reason = CLOSE_UNAUTHENTICATED, "sign in first"
    elif not signed_in:
        code, reason = CLOSE_UNAUTHENTICATED, "invalid or expired token; sign in again"
    else:
        # One reason for "no such room" and "not a member", so it doesn't say which rooms exist.
        code, reason = CLOSE_FORBIDDEN, f"no access to room {room_id}"
    logger.info("refused room=%s code=%d reason=%s", room_id, code, reason)
    await websocket.close(code=code, reason=reason)
    return None


async def _claim_origin(app, origin: str, user_id: int) -> int:
    """The origin's owner in the database, making it `user_id`'s if it has none yet."""
    owner_of = select(OriginOwner.user_id).where(OriginOwner.origin == origin)
    async with app.state.sessions() as session:
        owner = await session.scalar(owner_of)
        if owner is not None:
            return owner
        session.add(OriginOwner(origin=origin, user_id=user_id, claimed_at=datetime.now(UTC)))
        try:
            await session.commit()
        except IntegrityError:  # another connection claimed it at the same moment
            await session.rollback()
            return await session.scalar(owner_of)
        return user_id


async def _check_origin(websocket: WebSocket, room_id: str, access: Access, origin: str) -> None:
    """Raise ValueError unless this connection's user may send as `origin` (#10, #17)."""
    app = websocket.app
    registry = app.state.origins
    if registry.owner(origin) is None:
        owner = await app.state.tasks.shielded(_claim_origin(app, origin, access.user_id))
        registry.set_owner(origin, owner)
    registry.check(room_id, id(websocket), origin, access.user_id)


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


async def member_changed(room_id: str, user_id: int, role: Role | None) -> None:
    """Apply a membership change to the user's open connections to the room: a new role takes
    effect from their next message, and a removal (`role` None) closes them with 4403."""
    for websocket in manager.sockets(room_id):
        access = getattr(websocket.state, "access", None)
        if access is None or access.user_id != user_id:
            continue
        if role is not None:
            access.role = role
            logger.info("role change room=%s user=%s role=%s", room_id, access.username, role)
            continue
        access.removed = True
        manager.leave(room_id, websocket)  # no more broadcasts, even before its handler ends
        logger.info("removed room=%s user=%s", room_id, access.username)
        with suppress(Exception):  # already closing or gone: either way it's out
            await websocket.close(code=CLOSE_FORBIDDEN, reason=f"removed from room {room_id}")


def presence(room_id: str) -> list[dict]:
    """Who has an open socket in the room right now (#22): one entry per user, with their
    current role and how many connections they have (two Blenders count twice)."""
    users: dict[int, dict] = {}
    for websocket in manager.sockets(room_id):
        access = getattr(websocket.state, "access", None)
        if access is None or access.removed:
            continue
        entry = users.setdefault(
            access.user_id, {"username": access.username, "role": access.role, "connections": 0}
        )
        entry["connections"] += 1
    return sorted(users.values(), key=lambda entry: entry["username"])


@router.websocket("/ws/rooms/{room_id}")
async def room_socket(websocket: WebSocket, room_id: str) -> None:
    if not _ROOM_ID.match(room_id):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    with websocket.app.state.tasks.handler(websocket):
        access = await _authorize(websocket, room_id)
        if access is not None:
            websocket.state.access = access
            await _relay(websocket, room_id, access)


async def _relay(websocket: WebSocket, room_id: str, access: Access) -> None:
    app = websocket.app
    try:
        count = await _join_and_catch_up(websocket, room_id)
        logger.info(
            "connect room=%s user=%s role=%s clients=%d",
            room_id,
            access.username,
            access.role,
            count,
        )
        while True:
            raw = await websocket.receive_text()
            received_at = timing.now()
            if not can_send_operations(access.role):
                # Not parsed, logged or relayed: a viewer only watches.
                logger.info("reject room=%s user=%s reason=viewer", room_id, access.username)
                await _send_error(websocket, VIEWER_ERROR)
                continue
            try:
                message = parse_message(raw)
                await _check_origin(websocket, room_id, access, message.origin)
            except ValueError as exc:
                logger.info("reject room=%s reason=%s", room_id, exc)
                await _send_error(websocket, str(exc))
                continue
            except Exception:
                logger.exception("origin lookup failed room=%s", room_id)
                await _send_error(websocket, SAVE_ERROR)
                continue
            timing.mark("server_received", message, received_at)
            timing.mark("server_parsed", message)
            async with _room_lock(websocket, room_id):
                try:
                    seqs = await app.state.tasks.shielded(_append(app, room_id, message))
                except Exception:
                    logger.exception("append failed room=%s", room_id)
                    # Generic on purpose: database details stay in the server's log.
                    await _send_error(websocket, SAVE_ERROR)
                    continue
                timing.mark("server_persisted", message)
                await manager.broadcast(room_id, serialize_message(message), exclude=websocket)
                timing.mark("server_broadcast", message)
                app.state.snapshots.appended(room_id, len(seqs))
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        # Starlette's "send after close": the socket was closed under this handler when the
        # user was removed. Anything else is a real error.
        if not access.removed:
            raise
    finally:
        app.state.origins.release(room_id, id(websocket))
        count = manager.leave(room_id, websocket)
        logger.info("disconnect room=%s clients=%d", room_id, count)
