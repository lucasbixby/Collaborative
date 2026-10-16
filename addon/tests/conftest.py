"""Shared fixtures for headless add-on tests.

Tests run against the `bpy` module from PyPI: real Blender, no window. The add-on is
loaded through Blender's own add-on loader (addon_utils), the same path a user's
Blender takes, rather than by importing it directly.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

ADDON_NAME = "collaborative_blender"
ADDON_SOURCE = Path(__file__).resolve().parents[1] / ADDON_NAME

# Blender reads BLENDER_USER_SCRIPTS once, when bpy is first imported, so this must run
# before `import bpy`. A throwaway scripts folder keeps tests away from your real
# Blender preferences and add-ons.
_user_scripts = Path(tempfile.mkdtemp(prefix="collab-blender-"))
(_user_scripts / "addons").mkdir()
(_user_scripts / "addons" / ADDON_NAME).symlink_to(ADDON_SOURCE, target_is_directory=True)
os.environ["BLENDER_USER_SCRIPTS"] = str(_user_scripts)

import bpy  # noqa: I001  (must be imported before addon_utils)
import addon_utils


@pytest.fixture
def scene():
    """A fresh, empty scene for each test. Clears objects and non-persistent handlers."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


@pytest.fixture
def addon(scene):
    """The add-on enabled as Blender would enable it, and disabled again afterwards."""
    # On failure Blender prints the traceback (shown in pytest's captured output) and
    # returns None.
    module = addon_utils.enable(ADDON_NAME, default_set=True)
    assert module is not None, "Blender failed to enable the add-on; see captured stderr"
    yield module
    addon_utils.disable(ADDON_NAME, default_set=True)
    # Drop the cached module so the next test gets a clean import.
    for name in [m for m in sys.modules if m == ADDON_NAME or m.startswith(ADDON_NAME + ".")]:
        del sys.modules[name]


@pytest.fixture
def depsgraph_log(scene):
    """Records what Blender's depsgraph_update_post handler reports.

    Changes made from a script only reach the depsgraph when it is evaluated, so call
    `log.flush()` after making a change. It evaluates the scene and returns the updates
    recorded since the previous flush as (name, id type, transform?, geometry?) tuples.
    """
    log = _DepsgraphLog()
    bpy.app.handlers.depsgraph_update_post.append(log.handler)
    yield log
    if log.handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(log.handler)


class _DepsgraphLog:
    def __init__(self):
        self.updates = []

    def handler(self, scene, depsgraph):
        for update in depsgraph.updates:
            self.updates.append(
                (
                    update.id.name,
                    type(update.id).__name__,
                    update.is_updated_transform,
                    update.is_updated_geometry,
                )
            )

    def flush(self):
        bpy.context.view_layer.update()
        recorded, self.updates = self.updates, []
        return recorded
