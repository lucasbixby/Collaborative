"""Add-on preferences: server URL and auth token."""

import bpy


class CollaborativePreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    server_url: bpy.props.StringProperty(name="Server URL", default="ws://localhost:8000")
    auth_token: bpy.props.StringProperty(name="Auth token", subtype="PASSWORD")

    def draw(self, context):
        self.layout.prop(self, "server_url")
        self.layout.prop(self, "auth_token")


def register() -> None:
    bpy.utils.register_class(CollaborativePreferences)


def unregister() -> None:
    bpy.utils.unregister_class(CollaborativePreferences)
