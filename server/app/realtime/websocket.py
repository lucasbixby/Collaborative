"""WebSocket relay endpoint: one connection per client, one room per project (#11).

Minimal version for the prototype (10/24): no accounts (TODO #16 / #17), no ordering
beyond arrival order (#8 / #9), no persistence (#19). A room exists only while at least
one client is in it.

Flow for each incoming message:
  1. `parse_message` (app.sync.operations) checks size and schema.
  2. Valid: broadcast `serialize_message(parsed)` to every other client in the room, never
     back to the sender, which has already applied its own change. The re-serialized
     message is forwarded rather than the raw text, so only validated content leaves the
     server (docs/protocol.md).
  3. Invalid: reply to the sender only with an `error` message and keep the connection
     open. One bad batch shouldn't disconnect a client.
"""

import json
import logging
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.sync.operations import parse_message, serialize_message

from .connections import ConnectionManager

logger = logging.getLogger(__name__)
router = APIRouter()
manager = ConnectionManager()

ROOM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


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
            try:
                message = parse_message(raw)
            except ValueError as exc:
                logger.info("reject room=%s reason=%s", room_id, exc)
                error = {"v": 1, "type": "error", "message": str(exc)}
                await websocket.send_text(json.dumps(error))
                continue
            await manager.broadcast(room_id, serialize_message(message), exclude=websocket)
    except WebSocketDisconnect:
        pass
    finally:
        count = manager.leave(room_id, websocket)
        logger.info("disconnect room=%s clients=%d", room_id, count)
