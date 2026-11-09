"""Helpers for connecting a test client the way the add-on does since #20: every connection
starts with the room's catch-up (`ops` messages) and then one `synced`."""

import json
from contextlib import contextmanager

from tests.accounts import ensure_room, sign_in


def read_catch_up(ws) -> tuple[list[dict], int]:
    """Read the catch-up messages and the `synced` that ends them: (messages, seq)."""
    messages = []
    while True:
        message = json.loads(ws.receive_text())
        if message.get("type") == "synced":
            return messages, message["seq"]
        assert message.get("type") == "ops", message
        messages.append(message)


@contextmanager
def joined(test_client, room_id: str):
    """A socket in `room_id` that has already read its catch-up, kept as `ws.catch_up`. A
    client that isn't signed in yet is signed in as "tester" first (#16), and the room is
    created, with them as its owner, if it doesn't exist (#18)."""
    if "authorization" not in test_client.headers:
        sign_in(test_client)
    ensure_room(test_client, room_id)
    with test_client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
        ws.catch_up, ws.synced_seq = read_catch_up(ws)
        yield ws
