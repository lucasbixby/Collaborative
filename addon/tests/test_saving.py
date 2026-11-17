"""Tests for saving in a room: the host's save shares the file, a guest's save asks the host."""

import http.server
import json
import threading

import bpy
import pytest
from conftest import wait_until


class _FileServer:
    """Stands in for the server's `PUT /api/rooms/{room}/file`, recording each upload."""

    def __init__(self) -> None:
        self.uploads: list[dict] = []
        self.status = 200
        recorder = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_PUT(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                recorder.uploads.append(
                    {"path": self.path, "auth": self.headers["Authorization"], "body": body}
                )
                self.send_response(recorder.status)
                self.end_headers()
                self.wfile.write(b'{"name": "scene.blend"}')

            def log_message(self, *_args):
                pass

        self._server = http.server.ThreadingHTTPServer(("localhost", 0), Handler)
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self._server.shutdown()


@pytest.fixture
def files():
    server = _FileServer()
    yield server
    server.stop()


@pytest.fixture
def blend(tmp_path):
    """The current scene saved as a real .blend, as a launched Blender would have open."""
    path = str(tmp_path / "scene.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    return path


def _in_room(addon, relay, role, files=None):
    # One address serves both in production; here the socket and REST fakes are separate, so
    # the session points at the REST one once the socket is up.
    addon.session.configure(
        server_url=f"ws://localhost:{relay.port}", room="studio", token="t0k", role=role
    )
    bpy.ops.collaborative.join_room()
    wait_until(lambda: addon.client.status() == "connected" and relay._sockets)
    if files is not None:
        addon.session.current.server_url = f"http://localhost:{files.port}"


def test_the_hosts_save_uploads_the_saved_file(addon, relay, files, blend):
    _in_room(addon, relay, "owner", files)

    bpy.ops.wm.save_mainfile()

    wait_until(lambda: files.uploads and addon.saving.status == "Saved and shared with the room")
    upload = files.uploads[0]
    assert upload["path"] == "/api/rooms/studio/file?name=scene.blend"
    assert upload["auth"] == "Bearer t0k"
    with open(blend, "rb") as saved:
        assert upload["body"] == saved.read()
    assert relay.received == []  # nothing to ask anyone


def test_a_failed_upload_says_so(addon, relay, files, blend):
    files.status = 500
    _in_room(addon, relay, "owner", files)

    bpy.ops.wm.save_mainfile()

    wait_until(lambda: "sharing it failed" in addon.saving.status)


def test_a_guests_save_asks_the_host_instead_of_uploading(addon, relay, files, blend):
    _in_room(addon, relay, "editor", files)

    bpy.ops.wm.save_mainfile()

    wait_until(lambda: relay.received)
    assert json.loads(relay.received[0]) == {"v": 1, "type": "save_request"}
    assert files.uploads == []
    assert addon.saving.status == "Asked the host to save the project…"


def test_a_viewers_save_asks_nobody(addon, relay, files, blend):
    _in_room(addon, relay, "viewer", files)

    bpy.ops.wm.save_mainfile()

    assert relay.received == [] and files.uploads == []


def test_saving_outside_a_room_does_nothing(addon, files, blend):
    addon.session.configure()
    bpy.ops.wm.save_mainfile()
    assert files.uploads == [] and addon.saving.status == ""


def test_an_approved_request_makes_the_hosts_blender_save_and_share(addon, relay, files, blend):
    _in_room(addon, relay, "owner", files)
    bpy.data.objects.new("Added", None)

    relay.send_to_client(json.dumps({"v": 1, "type": "save", "requested_by": "bob"}))
    wait_until(lambda: addon.client._conn.inbox.qsize() >= 1)
    addon.client.drain()

    wait_until(lambda: files.uploads)
    assert not bpy.data.is_dirty


def test_a_guest_ignores_a_save_instruction(addon, relay, files, blend):
    _in_room(addon, relay, "editor", files)

    addon.saving.handle({"v": 1, "type": "save", "requested_by": "mallory"})

    assert files.uploads == [] and relay.received == []


@pytest.mark.parametrize(
    ("message", "shown"),
    [
        ({"type": "save_pending"}, "Waiting for the host to approve the save…"),
        ({"type": "save_result", "approved": True, "by": "alice"}, "alice approved your save"),
        ({"type": "save_result", "approved": False, "by": "alice"}, "alice declined your save"),
    ],
)
def test_the_guest_sees_how_their_request_went(addon, relay, message, shown):
    _in_room(addon, relay, "editor")

    relay.send_to_client(json.dumps({"v": 1, **message}))
    wait_until(lambda: addon.client._conn.inbox.qsize() >= 1)
    addon.client.drain()

    assert addon.saving.status == shown
