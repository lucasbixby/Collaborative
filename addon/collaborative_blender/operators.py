"""Operators the user triggers from the panel: join a room, leave a room."""

import json

import bpy

from . import detect
from .log import log


class COLLAB_OT_join_room(bpy.types.Operator):
    bl_idname = "collaborative.join_room"
    bl_label = "Join room"

    room_id: bpy.props.StringProperty(name="Room ID")

    def execute(self, context):
        # TODO: open the WebSocket (client.py) and start change detection (detect.py).
        self.report({"INFO"}, "Not implemented yet")
        return {"CANCELLED"}


class COLLAB_OT_leave_room(bpy.types.Operator):
    bl_idname = "collaborative.leave_room"
    bl_label = "Leave room"

    def execute(self, context):
        # TODO: stop detection, close the socket.
        return {"FINISHED"}


class COLLAB_OT_start_detection(bpy.types.Operator):
    """Dev aid (#5): run change detection without a server, logging each batch it would
    send. Superseded by Join room (#13), which will start detection itself."""

    bl_idname = "collaborative.start_detection"
    bl_label = "Start detection"

    def execute(self, context):
        detect.start(lambda message: log(json.dumps(message)))
        return {"FINISHED"}


class COLLAB_OT_stop_detection(bpy.types.Operator):
    bl_idname = "collaborative.stop_detection"
    bl_label = "Stop detection"

    def execute(self, context):
        detect.stop()
        return {"FINISHED"}


_classes = (
    COLLAB_OT_join_room,
    COLLAB_OT_leave_room,
    COLLAB_OT_start_detection,
    COLLAB_OT_stop_detection,
)


def register() -> None:
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
