"""WebSocket relay endpoint: one connection per client, one room per project (#11).

Minimal version for the prototype (10/24): no accounts (TODO #16 / #17), no ordering
beyond arrival order (#8 / #9). A room's connections exist only while at least one client
is in it, but its operations are kept in the log (#19).

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

import json
import logging
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.sync import log as operation_log
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


@router.websocket("/ws/rooms/{room_id}")
async def room_socket(websocket: WebSocket, room_id: str) -> None:
    if not ROOM_ID_PATTERN.match(room_id):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    count = manager.join(room_id, websocket)
    logger.info("connect room=%s clients=%d", room_id, count)

    try:
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
            try:
                async with websocket.app.state.sessions() as session:
                    await operation_log.append(session, room_id, message)
            except Exception:
                logger.exception("append failed room=%s", room_id)
                # Generic on purpose: database details stay in the server's log.
                await _send_error(websocket, "the server couldn't save this message; not relayed")
                continue
            timing.mark("server_persisted", message)
            await manager.broadcast(room_id, serialize_message(message), exclude=websocket)
            timing.mark("server_broadcast", message)
    except WebSocketDisconnect:
        pass
    finally:
        origins.release(room_id, id(websocket))
        count = manager.leave(room_id, websocket)
        logger.info("disconnect room=%s clients=%d", room_id, count)
