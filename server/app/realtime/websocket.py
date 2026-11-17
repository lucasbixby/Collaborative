"""WebSocket relay: one connection per Blender, one room per project.

Access: the token comes in the `Authorization: Bearer` header, never the URL (URLs are logged).
The socket is accepted, then closed before any catch-up with 4401 (no or bad token) or 4403 (no
such room, or not a member), so the client sees a code rather than a failed handshake.

Catch-up: under the room's lock, the socket joins the room, receives the room's state as
ordinary `ops` messages, then `synced`. The same lock is held around "append -> broadcast", so a
live op can't reach a client before its catch-up or fall between reading the state and joining.

Each incoming `ops` message is parsed and origin-checked, appended to the log, then broadcast
to everyone else from the validated model, never the raw text. A rejected message gets an
`error` reply and the connection stays open.

The handler never awaits the database directly: queries run through `tasks.shielded`, so a
client leaving mid-query can't leave a connection half-closed (app.realtime.tasks).
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
from app.auth.permissions import Role, can_join, can_manage, can_send_operations
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

# Application close codes (RFC 6455 7.4.2), named after HTTP's. Reconnecting can't help.
CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN = 4403

VIEWER_ERROR = "viewers can't edit"
SAVE_ERROR = "the server couldn't save this message; not relayed"
TEXT_ONLY_ERROR = "messages must be JSON text frames"

SAVE_REQUEST = {"v": 1, "type": "save_request"}
_CONTROL_MAX_BYTES = 64  # a control message is tiny; anything longer is parsed as `ops`


@dataclass
class Access:
    """Who a connection is signed in as, and their role in its room right now."""

    user_id: int
    username: str
    role: Role
    removed: bool = False  # set once the socket has been closed from the REST side


def _encode(message: dict) -> str:
    return json.dumps(message, separators=(",", ":"))


async def _send_error(websocket: WebSocket, reason: str) -> None:
    await websocket.send_text(_encode({"v": 1, "type": "error", "message": reason}))


def _room_lock(websocket: WebSocket, room_id: str) -> asyncio.Lock:
    # On `app.state`, not in this module: a lock belongs to one event loop, and each app
    # (each test) runs its own.
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
    """Raise ValueError unless this connection's user may send as `origin`."""
    app = websocket.app
    registry = app.state.origins
    if registry.owner(origin) is None:
        owner = await app.state.tasks.shielded(_claim_origin(app, origin, access.user_id))
        registry.set_owner(origin, owner)
    registry.check(room_id, id(websocket), origin, access.user_id)


async def _join_and_catch_up(websocket: WebSocket, room_id: str) -> int:
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


def _connections(room_id: str, user_id: int | None = None) -> list[tuple[WebSocket, Access]]:
    """The room's live connections with their access, optionally one user's only."""
    found = []
    for websocket in manager.sockets(room_id):
        access = getattr(websocket.state, "access", None)
        if access is None or access.removed:
            continue
        if user_id is None or access.user_id == user_id:
            found.append((websocket, access))
    return found


async def _close(room_id: str, websocket: WebSocket, access: Access, reason: str) -> None:
    access.removed = True
    manager.leave(room_id, websocket)  # no more broadcasts, even before its handler ends
    with suppress(Exception):  # already closing or gone: either way it's out
        await websocket.close(code=CLOSE_FORBIDDEN, reason=reason)


async def member_changed(room_id: str, user_id: int, role: Role | None) -> None:
    """Apply a membership change to the user's open connections: a new role takes effect from
    their next message, and a removal (`role` None) closes them with 4403."""
    for websocket, access in _connections(room_id, user_id):
        if role is not None:
            access.role = role
            logger.info("role change room=%s user=%s role=%s", room_id, access.username, role)
        else:
            logger.info("removed room=%s user=%s", room_id, access.username)
            await _close(room_id, websocket, access, f"removed from room {room_id}")


async def room_deleted(room_id: str) -> None:
    for websocket, access in _connections(room_id):
        await _close(room_id, websocket, access, f"room {room_id} was deleted")


async def send_to_user(room_id: str, user_id: int, message: dict) -> int:
    """Send a server message to every connection the user has in the room. Returns how many."""
    text = _encode(message)
    sent = 0
    for websocket, _access in _connections(room_id, user_id):
        with suppress(Exception):
            await websocket.send_text(text)
            sent += 1
    return sent


def presence(room_id: str) -> list[dict]:
    """Who has Blender connected to the room right now: one entry per user, with their role and
    how many connections they have."""
    users: dict[int, dict] = {}
    for _websocket, access in _connections(room_id):
        entry = users.setdefault(
            access.user_id, {"username": access.username, "role": access.role, "connections": 0}
        )
        entry["connections"] += 1
    return sorted(users.values(), key=lambda entry: entry["username"])


def _is_save_request(raw: str) -> bool:
    if len(raw) > _CONTROL_MAX_BYTES:
        return False
    try:
        return json.loads(raw) == SAVE_REQUEST
    except ValueError:
        return False


async def _handle_save_request(websocket: WebSocket, room_id: str, access: Access) -> None:
    """A guest saved in Blender: queue it for the host to approve. The host's own saves need no
    approval, and a viewer has nothing of theirs to save."""
    if can_manage(access.role):
        return
    if not can_send_operations(access.role):
        await _send_error(websocket, VIEWER_ERROR)
        return
    websocket.app.state.saves.add(room_id, access.user_id, access.username)
    logger.info("save requested room=%s user=%s", room_id, access.username)
    await websocket.send_text(_encode({"v": 1, "type": "save_pending"}))


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
            try:
                raw = await websocket.receive_text()
            except KeyError:  # a binary frame: Starlette has no "text" to return
                raw = None
            if not isinstance(raw, str):
                await _send_error(websocket, TEXT_ONLY_ERROR)
                continue
            received_at = timing.now()
            if _is_save_request(raw):
                await _handle_save_request(websocket, room_id, access)
                continue
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
                if access.removed:  # removed, or the room deleted, while this waited
                    break
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
        # user was removed or the room deleted. Anything else is a real error.
        if not access.removed:
            raise
    finally:
        app.state.origins.release(room_id, id(websocket))
        count = manager.leave(room_id, websocket)
        logger.info("disconnect room=%s clients=%d", room_id, count)
