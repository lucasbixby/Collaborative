"""Detect local scene changes and turn them into outgoing operations.

This is the day 1-3 spike from the proposal. Plan A: bpy.app.handlers.depsgraph_update_post.
Plan B (fallback): poll the synced properties on a short bpy.app.timers interval and diff.

Changes caused by applying a remote operation must be skipped (see apply.py) to avoid echo loops.
"""

# TODO: start(), stop(), and a diff of transforms / object set since the last check.
