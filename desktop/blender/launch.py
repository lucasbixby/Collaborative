"""Run by Blender when the Collaborative app launches it: `blender file.blend --python launch.py`.

Loads the Collaborative add-on from the app's own copy (COLLAB_ADDON_DIR) for this session
only, so nothing has to be installed in Blender and nothing is written to the user's
preferences. The add-on then joins the room named in the environment by itself.
"""

import os
import sys

ADDON = "collaborative_blender"

# Already loaded when a developer has the add-on linked into their own Blender: it registered
# itself at startup, read the same environment, and is joining the room already.
if ADDON not in sys.modules:
    sys.path.insert(0, os.environ["COLLAB_ADDON_DIR"])
    __import__(ADDON).register()
