"""Joining and leaving the session's room: from the panel's buttons, and automatically when the
app has just launched Blender into a room."""

import bpy
from bpy.app.handlers import persistent

from . import apply, client, detect, ids, ordering, panel, saving, session
from .log import log

_AUTO_JOIN_DELAY = 0.2  # seconds after the add-on registers, so the file is fully loaded


def join_room() -> None:
    """Connect to the session's room and start syncing. Raises ValueError for a bad room name."""
    current = session.current
    client.connect(
        current.server_url,
        current.room,
        apply.apply_message,
        detect.send_unknown_creates,
        token=current.token,
        on_control=saving.handle,
    )
    ids.assign_shared_ids(current.room)
    # stop() first: start() does nothing while detection is already running, which would leave
    # edits going to whatever the previous room wired up.
    detect.stop()
    if current.can_edit:
        detect.start(client.send)
    panel.start_status_watch()


def leave_room() -> None:
    detect.stop()
    client.disconnect()
    panel.stop_status_watch()


def _auto_join() -> None:
    try:
        join_room()
    except ValueError as exc:
        log("couldn't join:", exc)


def join_when_ready() -> None:
    """Join the session's room once Blender has finished starting, if the app set one."""
    if session.current.room and not bpy.app.timers.is_registered(_auto_join):
        bpy.app.timers.register(_auto_join, first_interval=_AUTO_JOIN_DELAY)


class COLLAB_OT_join_room(bpy.types.Operator):
    """Connect to the room again"""

    bl_idname = "collaborative.join_room"
    bl_label = "Rejoin room"

    @classmethod
    def poll(cls, context) -> bool:
        # "refused" too: once access is sorted out in the app, this is how to try again.
        return bool(session.current.room) and client.status() in ("disconnected", "refused")

    def execute(self, context):
        try:
            join_room()
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class COLLAB_OT_leave_room(bpy.types.Operator):
    """Stop syncing with the room. Your scene stays as it is"""

    bl_idname = "collaborative.leave_room"
    bl_label = "Leave room"

    @classmethod
    def poll(cls, context) -> bool:
        return client.status() != "disconnected"

    def execute(self, context):
        leave_room()
        return {"FINISHED"}


@persistent
def _on_load_pre(*_args) -> None:
    """A different file is about to load: detect's cache, the object IDs and the tombstones all
    belong to the one being replaced, so leave the room rather than sync the wrong scene."""
    if client.status() != "disconnected":
        log("leaving the room: a different file is being opened")
    leave_room()
    ordering.tombstones.clear()


_classes = (COLLAB_OT_join_room, COLLAB_OT_leave_room)


def register() -> None:
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.app.handlers.load_pre.append(_on_load_pre)


def unregister() -> None:
    if bpy.app.timers.is_registered(_auto_join):
        bpy.app.timers.unregister(_auto_join)
    if _on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load_pre)
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
