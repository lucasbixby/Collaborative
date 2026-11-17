"""Collaborative: the Blender side of a shared room.

The Collaborative app starts Blender with this add-on and the room to join (session.py), so
there is nothing to install or type by hand; see desktop/blender/launch.py.
"""

bl_info = {
    "name": "Collaborative",
    "author": "Lucas Bixby",
    "version": (0, 2, 0),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > Collaborative",
    "description": "Edit the same scene live with other people through a shared room",
    "category": "System",
}

from . import client, detect, operators, panel, saving

_modules = (operators, panel, saving)


def register() -> None:
    for module in _modules:
        module.register()
    operators.join_when_ready()


def unregister() -> None:
    client.disconnect()
    detect.stop()
    for module in reversed(_modules):
        module.unregister()
