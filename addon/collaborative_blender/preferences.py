"""Add-on preferences: server URL, and signing in (#16).

Sign in asks for a username and password, trades them for a token (account.py) and keeps only
the token, in `auth_token`. The password is an operator property marked SKIP_SAVE, so Blender
doesn't remember it as the "last used" value. Sign out just forgets the token here; the server
has no revocation, so the token itself stays valid until it expires.
"""

import bpy

from . import account

ADDON = __name__.partition(".")[0]  # the add-on package name


def prefs(context=None) -> "CollaborativePreferences":
    return (context or bpy.context).preferences.addons[ADDON].preferences


class CollaborativePreferences(bpy.types.AddonPreferences):
    bl_idname = ADDON

    server_url: bpy.props.StringProperty(name="Server URL", default="ws://localhost:8000")
    auth_token: bpy.props.StringProperty(name="Auth token", subtype="PASSWORD")
    signed_in_as: bpy.props.StringProperty(name="Signed in as")

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "server_url")
        if self.auth_token:
            row = layout.row()
            row.label(text=f"Signed in as {self.signed_in_as or '(a pasted token)'}")
            row.operator("collaborative.sign_out")
        else:
            layout.operator("collaborative.sign_in")
        layout.prop(self, "auth_token")


class COLLAB_OT_sign_in(bpy.types.Operator):
    """Sign in to the server and keep the token in Preferences (the password isn't kept)"""

    bl_idname = "collaborative.sign_in"
    bl_label = "Sign in"

    username: bpy.props.StringProperty(name="Username", options={"SKIP_SAVE"})
    password: bpy.props.StringProperty(
        name="Password", subtype="PASSWORD", options={"SKIP_SAVE"}
    )

    def invoke(self, context, event):
        self.username = prefs(context).signed_in_as
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        settings = prefs(context)
        try:
            token, username = account.login(settings.server_url, self.username, self.password)
        except account.SignInError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        finally:
            self.password = ""
        settings.auth_token = token
        settings.signed_in_as = username
        self.report({"INFO"}, f"Signed in as {username}")
        return {"FINISHED"}


class COLLAB_OT_sign_out(bpy.types.Operator):
    """Forget the token on this computer"""

    bl_idname = "collaborative.sign_out"
    bl_label = "Sign out"

    def execute(self, context):
        settings = prefs(context)
        settings.auth_token = ""
        settings.signed_in_as = ""
        return {"FINISHED"}


_classes = (CollaborativePreferences, COLLAB_OT_sign_in, COLLAB_OT_sign_out)


def register() -> None:
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
