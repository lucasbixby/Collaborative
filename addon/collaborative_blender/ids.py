"""Stable object IDs (#4): `obj["collab_id"]` identifies an object across the sync protocol.

Blender's own `session_uid` can't fill that role: it's reassigned on every file reopen, so
it can't be sent to the server or compared across sessions. A UUID stored as a custom
property survives renames, copies and save/reopen, and setting it fires no depsgraph
update, so assigning one never triggers a spurious sync.
"""

import uuid

import bpy

COLLAB_ID = "collab_id"


def get_id(obj: bpy.types.Object) -> str | None:
    """The object's `collab_id`, or None if it doesn't have one yet."""
    return obj.get(COLLAB_ID)


def find_object(collab_id: str) -> bpy.types.Object | None:
    """The scene object carrying `collab_id`, or None if there isn't one."""
    for obj in bpy.context.scene.objects:
        if obj.get(COLLAB_ID) == collab_id:
            return obj
    return None


def ensure_ids() -> list[bpy.types.Object]:
    """Give every scene object a `collab_id`. Returns the objects that got a new one.

    Shift+D, Alt+D and `obj.copy()` all copy `collab_id` along with the object, so a copy
    briefly shares its ID with the original. Blender always gives a copy a higher
    `session_uid` than the object it was copied from, so the lowest `session_uid` keeps the
    shared ID and every other holder is treated as a copy and given a fresh one.
    """
    by_id: dict[str, list[bpy.types.Object]] = {}
    new_ids: list[bpy.types.Object] = []

    for obj in bpy.context.scene.objects:
        collab_id = get_id(obj)
        if collab_id is None:
            new_ids.append(obj)
        else:
            by_id.setdefault(collab_id, []).append(obj)

    for holders in by_id.values():
        if len(holders) > 1:
            holders.sort(key=lambda obj: obj.session_uid)
            new_ids.extend(holders[1:])

    for obj in new_ids:
        obj[COLLAB_ID] = str(uuid.uuid4())

    return new_ids
