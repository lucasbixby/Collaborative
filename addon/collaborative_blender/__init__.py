"""Collaborative — Blender add-on entry point.

Install by zipping this folder (see addon/README.md) and adding it in
Edit > Preferences > Add-ons > Install from Disk.
"""

bl_info = {
    "name": "Collaborative",
    "author": "Lucas Bixby",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Collaborative",
    "description": "Edit the same scene live with other people through a shared room",
    "category": "System",
}

from . import operators, panel, preferences  # noqa: E402

_modules = (preferences, operators, panel)


def register() -> None:
    for module in _modules:
        module.register()


def unregister() -> None:
    for module in reversed(_modules):
        module.unregister()
