"""Operators the user triggers from the panel: join a room, leave a room."""

import bpy


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


_classes = (COLLAB_OT_join_room, COLLAB_OT_leave_room)


def register() -> None:
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
