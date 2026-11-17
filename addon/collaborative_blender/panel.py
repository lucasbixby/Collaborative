"""Sidebar panel in the 3D viewport: which room this Blender is in, and how the connection and
the last save are doing."""

import bpy

from . import client, saving, session

_STATUS_WATCH_INTERVAL = 0.25  # seconds
_last_seen: tuple | None = None

_STATUS_TEXT = {
    "disconnected": "Not connected",
    "connecting": "Connecting to {room}…",
    "syncing": "Catching up with {room}…",
    "connected": "Connected to {room}",
    "reconnecting": "Reconnecting to {room}…",
}

# Why the server refused the connection; the client has stopped retrying.
_REFUSAL_TEXT = {
    client.CLOSE_UNAUTHENTICATED: "Signed out: launch again from the Collaborative app",
    client.CLOSE_FORBIDDEN: "No access to {room}",
}

_ROLE_TEXT = {
    "owner": "You're the host: saving updates the project for everyone",
    "editor": "Saving asks the host to save the project",
    "viewer": "You're viewing: your own edits stay on this computer",
}


class COLLAB_PT_main(bpy.types.Panel):
    bl_label = "Collaborative"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Collaborative"

    def draw(self, context):
        layout = self.layout
        current = session.current
        if not current.room:
            layout.label(text="Open a room from the Collaborative app")
            return

        layout.label(text=status_text(current.room), icon="WORLD")
        if current.username:
            layout.label(text=f"Signed in as {current.username}", icon="USER")
        layout.label(text=_ROLE_TEXT.get(current.role, ""))
        if saving.status:
            layout.label(text=saving.status, icon="FILE_TICK")
        row = layout.row()
        row.operator("collaborative.join_room")
        row.operator("collaborative.leave_room")


def status_text(room: str) -> str:
    shown = _shown_status()
    if shown == "refused":
        code, reason = client.refusal() or (None, "")
        return _REFUSAL_TEXT.get(code, "Refused by the server: {reason}").format(
            room=room, reason=reason
        )
    return _STATUS_TEXT[shown].format(room=room)


def _shown_status() -> str:
    """The client's status, with "connected" split until the room's catch-up is in."""
    current = client.status()
    if current == "connected" and not client.synced():
        return "syncing"
    return current


def _tag_redraw_viewports() -> None:
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for region in area.regions:
                if region.type == "UI":
                    region.tag_redraw()


def _watch_status() -> float:
    """Blender only redraws a panel on mouse hover, but the connection and save status change
    on background threads, so this timer asks for a redraw when what the panel shows changes."""
    global _last_seen
    current = (client.status(), client.synced(), saving.status)
    if current != _last_seen:
        _last_seen = current
        _tag_redraw_viewports()
    return _STATUS_WATCH_INTERVAL


def start_status_watch() -> None:
    global _last_seen
    _last_seen = None
    if not bpy.app.timers.is_registered(_watch_status):
        bpy.app.timers.register(
            _watch_status, first_interval=_STATUS_WATCH_INTERVAL, persistent=True
        )


def stop_status_watch() -> None:
    if bpy.app.timers.is_registered(_watch_status):
        bpy.app.timers.unregister(_watch_status)


def register() -> None:
    bpy.utils.register_class(COLLAB_PT_main)


def unregister() -> None:
    stop_status_watch()
    bpy.utils.unregister_class(COLLAB_PT_main)
