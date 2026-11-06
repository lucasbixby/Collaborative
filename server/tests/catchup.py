"""Helpers for connecting a test client the way the add-on does since #20: every connection
starts with the room's catch-up (`ops` messages) and then one `synced`."""

import json
from contextlib import contextmanager


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
    """A socket in `room_id` that has already read its catch-up, kept as `ws.catch_up`."""
    with test_client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
        ws.catch_up, ws.synced_seq = read_catch_up(ws)
        yield ws
