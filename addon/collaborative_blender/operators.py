"""Operators the user triggers from the panel: join a room, leave a room."""

import json

import bpy
from bpy.app.handlers import persistent

from . import apply, client, detect, panel
from .log import log


class COLLAB_OT_join_room(bpy.types.Operator):
    """Connect to the server and start sending/receiving operations for this room."""

    bl_idname = "collaborative.join_room"
    bl_label = "Join room"

    @classmethod
    def poll(cls, context) -> bool:
        return client.status() == "disconnected"

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        room_id = context.window_manager.room_id
        try:
            client.connect(prefs.server_url, room_id, apply.apply_message)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        # stop() first: if the old Start detection dev aid (or a previous room) left
        # detection running, start() would be a no-op and edits would never be sent.
        detect.stop()
        detect.start(client.send)
        panel.start_status_watch()
        return {"FINISHED"}


class COLLAB_OT_leave_room(bpy.types.Operator):
    bl_idname = "collaborative.leave_room"
    bl_label = "Leave room"

    @classmethod
    def poll(cls, context) -> bool:
        return client.status() != "disconnected"

    def execute(self, context):
        _leave_room()
        return {"FINISHED"}


def _leave_room() -> None:
    """The shared Leave action: used by the operator above and by `_on_load_pre`."""
    detect.stop()
    client.disconnect()
    panel.stop_status_watch()


@persistent
def _on_load_pre(*_args) -> None:
    """Opening another file would otherwise leave the client connected while detect's
    cache and the scene's `collab_id`s still belong to the file being replaced (#13)."""
    if client.status() != "disconnected":
        log("leaving the room: a different file is being opened")
    _leave_room()


class COLLAB_OT_apply_from_clipboard(bpy.types.Operator):
    """Dev aid (#6): parse the clipboard as one `ops` message and apply it to the local
    scene. Accepts a line copied straight from the detection log (its `[collab A ...]`
    prefix is dropped). Still handy for checking last-writer-wins (#8/#9) by hand."""

    bl_idname = "collaborative.apply_from_clipboard"
    bl_label = "Apply from clipboard"

    def execute(self, context):
        text = context.window_manager.clipboard
        start = text.find("{")
        if start == -1:
            self.report({"ERROR"}, "Clipboard has no JSON object")
            return {"CANCELLED"}
        try:
            message = json.loads(text[start:])
        except json.JSONDecodeError as exc:
            self.report({"ERROR"}, f"Invalid JSON: {exc}")
            return {"CANCELLED"}
        apply.apply_message(message)
        return {"FINISHED"}


_classes = (
    COLLAB_OT_join_room,
    COLLAB_OT_leave_room,
    COLLAB_OT_apply_from_clipboard,
)


def register() -> None:
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.app.handlers.load_pre.append(_on_load_pre)


def unregister() -> None:
    if _on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load_pre)
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
