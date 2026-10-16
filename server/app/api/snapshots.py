"""REST: room snapshots and operation history, used for catch-up after reconnect."""

from fastapi import APIRouter

router = APIRouter()

# TODO: GET /{room_id}/snapshot (latest), GET /{room_id}/operations?since=<lamport>
