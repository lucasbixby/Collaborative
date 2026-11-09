"""Who may connect to a room's socket and send to it (#16, #17)."""

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.accounts import bearer, token_for
from tests.catchup import read_catch_up


def _refusal(test_client, room_id, headers=None) -> tuple[int, str]:
    """Connect, and return the close code and reason the server ends the socket with."""
    with (
        test_client.websocket_connect(f"/ws/rooms/{room_id}", headers=headers or {}) as ws,
        pytest.raises(WebSocketDisconnect) as closed,
    ):
        ws.receive_text()
    return closed.value.code, closed.value.reason


def test_no_token_is_closed_with_4401(anon):
    assert _refusal(anon, "demo") == (4401, "sign in first")


@pytest.mark.parametrize(
    "header", ["Bearer not-a-token", "Basic YWxpY2U6cHc=", "Bearer ", "token-without-scheme"]
)
def test_a_bad_token_is_closed_with_4401(anon, header):
    code, _reason = _refusal(anon, "demo", {"Authorization": header})
    assert code == 4401


def test_a_token_in_the_query_string_is_ignored(anon):
    token = token_for(anon, "alice")
    with (
        anon.websocket_connect(f"/ws/rooms/demo?token={token}") as ws,
        pytest.raises(WebSocketDisconnect) as closed,
    ):
        ws.receive_text()
    assert closed.value.code == 4401


def test_a_valid_token_gets_catch_up(anon):
    token = token_for(anon, "alice")
    with anon.websocket_connect("/ws/rooms/demo", headers=bearer(token)) as ws:
        assert read_catch_up(ws) == ([], 0)
