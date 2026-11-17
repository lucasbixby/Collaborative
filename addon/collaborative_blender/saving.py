"""Saving in a shared room.

The project file belongs to the host. When the host saves, Blender writes their real file as
usual and this module uploads it, so the next person to launch gets it. When anyone else saves,
Blender only writes their local working copy, and this module asks the host instead; if the
host approves, the server tells the host's Blender to save, which lands back here as a host
save. `status` is the line the panel shows.
"""

import json
import os
import shutil
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request

import bpy
from bpy.app.handlers import persistent

from . import client, session
from .log import log

UPLOAD_TIMEOUT = 300  # seconds

status = ""
_upload_lock = threading.Lock()
_upload_again = False


def _set_status(text: str) -> None:
    global status
    status = text


def upload(http_url: str, token: str, room: str, path: str, name: str) -> dict:
    """PUT the file at `path` as the room's project file, shown to others as `name`. Blocking:
    call it off the main thread."""
    with open(path, "rb") as file:
        request = urllib.request.Request(
            f"{http_url}/api/rooms/{urllib.parse.quote(room)}/file?name={urllib.parse.quote(name)}",
            data=file,
            method="PUT",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/octet-stream",
                "Content-Length": str(os.fstat(file.fileno()).st_size),
            },
        )
        with urllib.request.urlopen(request, timeout=UPLOAD_TIMEOUT) as response:
            return json.loads(response.read())


def _upload_in_background(current: session.Session, path: str) -> None:
    """Upload a copy of the saved file. A save that lands while one upload is running is
    uploaded straight after it, so the server always ends with the latest."""
    global _upload_again
    if not _upload_lock.acquire(blocking=False):
        _upload_again = True
        return
    try:
        while True:
            _upload_again = False
            # A private copy first: Blender may save again while this is still sending.
            fd, copy = tempfile.mkstemp(suffix=".blend")
            os.close(fd)
            try:
                shutil.copyfile(path, copy)
                upload(current.http_url, current.token, current.room, copy, os.path.basename(path))
                _set_status("Saved and shared with the room")
            except (OSError, ValueError, urllib.error.URLError) as exc:
                log("saving: upload failed", exc)
                _set_status("Saved here, but sharing it failed (see the terminal)")
            finally:
                os.unlink(copy)
            if not _upload_again:
                return
    finally:
        _upload_lock.release()


@persistent
def _on_save_post(*_args) -> None:
    current = session.current
    if not current.room or client.status() != "connected":
        return
    if current.is_host:
        path = bpy.data.filepath
        if not path:
            return
        _set_status("Saved. Sharing with the room…")
        target = os.path.basename(path)
        threading.Thread(
            target=_upload_in_background, args=(current, path), name=f"upload {target}", daemon=True
        ).start()
    elif current.can_edit:
        client.send_control({"v": 1, "type": "save_request"})
        _set_status("Asked the host to save the project…")


def handle(message: dict) -> None:
    """A save message from the server, on the main thread (from `client.drain`)."""
    kind = message.get("type")
    if kind == "save_pending":
        _set_status("Waiting for the host to approve the save…")
    elif kind == "save_result":
        verdict = "approved" if message.get("approved") else "declined"
        _set_status(f"{message.get('by', 'The host')} {verdict} your save")
    elif kind == "save" and session.current.is_host:
        log("saving: approved a save requested by", message.get("requested_by"))
        try:
            bpy.ops.wm.save_mainfile()  # runs _on_save_post, which shares the file
        except RuntimeError as exc:
            log("saving: could not save", exc)
            _set_status("Couldn't save the project (see the terminal)")


def register() -> None:
    bpy.app.handlers.save_post.append(_on_save_post)


def unregister() -> None:
    if _on_save_post in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(_on_save_post)
