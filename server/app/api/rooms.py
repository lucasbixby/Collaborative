"""REST: create rooms, generate invite links, list a user's rooms, manage members."""

from fastapi import APIRouter

router = APIRouter()

# TODO: POST / (create room), GET / (my rooms), POST /{room_id}/invites, POST /join/{invite_code}
