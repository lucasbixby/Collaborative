"""Sidebar panel in the 3D viewport showing room and connection status."""

import bpy

from . import client

_STATUS_WATCH_INTERVAL = 0.25  # seconds
_last_seen_status: str | None = None

_STATUS_TEXT = {
    "disconnected": "Not connected",
    "connecting": "Connecting to {room}…",
    "connected": "Connected to {room}",
    "reconnecting": "Reconnecting to {room}…",
}


class COLLAB_PT_main(bpy.types.Panel):
    bl_label = "Collaborative"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Collaborative"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        current_status = client.status()

        row = layout.row()
        row.enabled = current_status == "disconnected"
        row.prop(wm, "room_id", text="Room")

        status_text = _STATUS_TEXT[current_status].format(room=wm.room_id)
        layout.label(text=f"Status: {status_text}")
        layout.operator("collaborative.join_room")
        layout.operator("collaborative.leave_room")

        layout.separator()
        layout.label(text="Apply (dev aid, #6)")
        layout.operator("collaborative.apply_from_clipboard")


def _tag_redraw_viewports() -> None:
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for region in area.regions:
                if region.type == "UI":
                    region.tag_redraw()


def _watch_status() -> float:
    """Blender only redraws the panel on mouse hover, but `client.status()` changes on
    a background thread, so this timer polls it and asks for a redraw when it changes.
    Reads `status()` only — never touches the socket."""
    global _last_seen_status
    current = client.status()
    if current != _last_seen_status:
        _last_seen_status = current
        _tag_redraw_viewports()
    return _STATUS_WATCH_INTERVAL


def start_status_watch() -> None:
    """Start polling `client.status()` for redraws. Called by Join; safe to call again."""
    global _last_seen_status
    _last_seen_status = None
    if not bpy.app.timers.is_registered(_watch_status):
        bpy.app.timers.register(
            _watch_status, first_interval=_STATUS_WATCH_INTERVAL, persistent=True
        )


def stop_status_watch() -> None:
    """Stop polling. Called by Leave (and the `load_pre` handler); safe to call anytime."""
    if bpy.app.timers.is_registered(_watch_status):
        bpy.app.timers.unregister(_watch_status)


def register() -> None:
    bpy.types.WindowManager.room_id = bpy.props.StringProperty(
        name="Room ID",
        description="Room to join on the relay server",
        default="demo",
    )
    bpy.utils.register_class(COLLAB_PT_main)


def unregister() -> None:
    bpy.utils.unregister_class(COLLAB_PT_main)
    del bpy.types.WindowManager.room_id
