"""Detect local scene changes and turn them into outgoing operations.

This is the day 1-3 spike from the proposal. Plan A: bpy.app.handlers.depsgraph_update_post.
Plan B (fallback): poll the synced properties on a short bpy.app.timers interval and diff.

Changes caused by applying a remote operation must be skipped (see apply.py) to avoid echo loops.
"""

# TODO: start(), stop(), and a diff of transforms / object set since the last check.

import bpy
from bpy.app.handlers import persistent
from .log import log

@persistent
def _on_depsgraph_update(scene, depsgraph):
    for u in depsgraph.updates:
        flags = [n for n, on in (("transform", u.is_updated_transform),
                                  ("geometry", u.is_updated_geometry)) if on]
        log(type(u.id).__name__, u.id.original.name, *flags)

def start():
    if _on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)

def stop():
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)