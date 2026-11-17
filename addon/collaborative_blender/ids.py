"""Stable object IDs: `obj["collab_id"]` identifies an object across the sync protocol.

Blender's own `session_uid` changes on every file open, so it can't be sent to anyone. A UUID in
a custom property survives renames, copies and save/reopen, and setting it fires no depsgraph
update, so assigning one never looks like an edit.
"""

import uuid

import bpy

COLLAB_ID = "collab_id"
SHARED_IDS_DONE = "collab_shared_ids"  # on the scene: its objects have had their shared IDs
_NAMESPACE = uuid.UUID("7b0c2f4e-5d1a-4c3b-9e8f-0a1b2c3d4e5f")


def get_id(obj: bpy.types.Object) -> str | None:
    return obj.get(COLLAB_ID)


def find_object(collab_id: str) -> bpy.types.Object | None:
    for obj in bpy.context.scene.objects:
        if obj.get(COLLAB_ID) == collab_id:
            return obj
    return None


def assign_new_id(obj: bpy.types.Object) -> str:
    """Give `obj` a fresh random `collab_id`, replacing any it had."""
    collab_id = str(uuid.uuid4())
    obj[COLLAB_ID] = collab_id
    return collab_id


def assign_shared_ids(room: str) -> None:
    """Give every object that has no ID yet one derived from the room and the object's name.

    Everyone in a room opens the same project file, and object names are unique within a file,
    so each person's Blender arrives at the same ID for the same object without the file having
    to be changed first. This runs once per file: the scene is then marked (and the IDs are
    saved with it), so an object added later is new, and gets a random ID from `ensure_ids`
    rather than the ID of whatever used to have its name.
    """
    scene = bpy.context.scene
    if scene.get(SHARED_IDS_DONE):
        return
    for obj in scene.objects:
        if get_id(obj) is None:
            obj[COLLAB_ID] = str(uuid.uuid5(_NAMESPACE, f"{room}/{obj.name}"))
    scene[SHARED_IDS_DONE] = True


def ensure_ids() -> list[bpy.types.Object]:
    """Give every scene object a `collab_id`. Returns the objects that got a new one.

    A copy (Shift+D, Alt+D, `obj.copy()`) carries its source's ID. Blender always gives a copy
    a higher `session_uid`, so the lowest keeps the shared ID and the rest get fresh ones.
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
        assign_new_id(obj)

    return new_ids
