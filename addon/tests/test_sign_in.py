"""Tests for signing in from Preferences (#16) and the panel's refusal text (#16, #17), with a
fake login endpoint on a local HTTP server.

Tests that need the add-on use its modules through the `addon` fixture (`addon.client`), since
the fixture re-imports the package for every test (see test_join_leave.py).
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import bpy
import pytest
from conftest import wait_until

from collaborative_blender import account


class _FakeLogin(BaseHTTPRequestHandler):
    """Answers POST /api/auth/login like the server: a token for alice/right-password."""

    requests: ClassVar[list[tuple[str, dict]]] = []

    def do_POST(self):  # the name http.server looks for
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append((self.path, body))
        if self.path == "/api/auth/login" and body == {
            "username": "alice",
            "password": "right-password",
        }:
            self._reply(200, {"token": "tok-123", "user": {"id": 1, "username": "alice"}})
        elif self.path == "/api/auth/login":
            self._reply(401, {"detail": "wrong username or password"})
        else:
            self._reply(404, {"detail": "Not Found"})

    def _reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def login_server():
    _FakeLogin.requests = []
    server = ThreadingHTTPServer(("localhost", 0), _FakeLogin)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def prefs(addon):
    yield bpy.context.preferences.addons["collaborative_blender"].preferences
    addon.client.disconnect()


@pytest.mark.parametrize(
    ("server_url", "expected"),
    [
        ("ws://localhost:8000", "http://localhost:8000"),
        ("wss://collab.example.com/", "https://collab.example.com"),
        (" http://10.0.0.5:8000 ", "http://10.0.0.5:8000"),
    ],
)
def test_http_url(server_url, expected):
    assert account.http_url(server_url) == expected


def test_sign_in_saves_the_token_and_name_not_the_password(prefs, login_server):
    prefs.server_url = f"ws://localhost:{login_server.server_port}"

    result = bpy.ops.collaborative.sign_in(username="alice", password="right-password")

    assert result == {"FINISHED"}
    assert (prefs.auth_token, prefs.signed_in_as) == ("tok-123", "alice")
    assert _FakeLogin.requests == [
        ("/api/auth/login", {"username": "alice", "password": "right-password"})
    ]
    # SKIP_SAVE: the next Sign in doesn't start with the last password filled in.
    last_used = bpy.context.window_manager.operator_properties_last("collaborative.sign_in")
    assert last_used.password == ""


def test_a_wrong_password_keeps_the_old_state(prefs, login_server):
    prefs.server_url = f"ws://localhost:{login_server.server_port}"

    with pytest.raises(RuntimeError, match="Wrong username or password"):
        bpy.ops.collaborative.sign_in(username="alice", password="nope")

    assert prefs.auth_token == ""


def test_an_unreachable_server_is_reported(prefs, login_server):
    port = login_server.server_port
    login_server.shutdown()
    login_server.server_close()
    prefs.server_url = f"ws://localhost:{port}"

    with pytest.raises(RuntimeError, match="Couldn't reach http://localhost"):
        bpy.ops.collaborative.sign_in(username="alice", password="right-password")


def test_sign_out_forgets_the_token(prefs):
    prefs.auth_token, prefs.signed_in_as = "tok-123", "alice"

    assert bpy.ops.collaborative.sign_out() == {"FINISHED"}

    assert (prefs.auth_token, prefs.signed_in_as) == ("", "")


def test_join_sends_the_saved_token(prefs, relay):
    prefs.server_url = f"ws://localhost:{relay.port}"
    prefs.auth_token = "tok-123"

    assert bpy.ops.collaborative.join_room() == {"FINISHED"}

    wait_until(lambda: relay.authorizations == ["Bearer tok-123"])


@pytest.mark.parametrize(
    ("code", "text"),
    [
        (4401, "Sign in first (Preferences > Add-ons > Collaborative)"),
        (4403, "No access to demo"),
    ],
)
def test_the_panel_says_why_the_server_refused(addon, prefs, relay, code, text):
    relay.refuse_with = (code, "whatever the server said")
    prefs.server_url = f"ws://localhost:{relay.port}"
    bpy.ops.collaborative.join_room()

    wait_until(lambda: addon.client.status() == "refused")

    assert addon.panel.status_text("demo") == text
    # Join is offered again, so signing in (or being invited) and retrying is one click.
    assert bpy.ops.collaborative.join_room.poll()
