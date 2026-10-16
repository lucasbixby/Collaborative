"""WebSocket relay endpoint: one connection per client, one room per project.

Flow for each incoming message (proposal, "How one change travels"):
  1. Authenticate the socket (token on connect) and check room membership.
  2. Hand the raw operation to the sync engine (app.sync) to validate and order it.
  3. Append to the operation log, then broadcast to the other clients in the room.
"""

from fastapi import APIRouter, WebSocket

router = APIRouter()


@router.websocket("/ws/rooms/{room_id}")
async def room_socket(websocket: WebSocket, room_id: str) -> None:
    # TODO: authenticate, register with ConnectionManager, receive/relay loop.
    await websocket.close(code=1013, reason="Not implemented yet")
