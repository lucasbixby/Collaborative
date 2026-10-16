"""The add-on loads, registers its UI and operators, and unloads cleanly.

Clean unregistration matters during development: Reload Scripts and the VS Code
extension's reload-on-save both disable and re-enable the add-on.
"""

import bpy  # noqa: I001  (must be imported before addon_utils)
import addon_utils
from conftest import ADDON_NAME


def test_enables_and_registers_ui(addon):
    assert hasattr(bpy.types, "COLLAB_PT_main")
    # Operators are registered under their bl_idname ("collaborative.join_room").
    assert hasattr(bpy.types, "COLLABORATIVE_OT_join_room")
    assert hasattr(bpy.types, "COLLABORATIVE_OT_leave_room")


def test_bl_info_targets_supported_blender(addon):
    assert tuple(addon.bl_info["blender"]) <= bpy.app.version


def test_disable_removes_everything(scene):
    addon_utils.enable(ADDON_NAME, default_set=True)
    addon_utils.disable(ADDON_NAME, default_set=True)
    assert not hasattr(bpy.types, "COLLAB_PT_main")


def test_can_be_reloaded_repeatedly(scene):
    for _ in range(3):
        assert addon_utils.enable(ADDON_NAME, default_set=True) is not None
        addon_utils.disable(ADDON_NAME, default_set=True)
