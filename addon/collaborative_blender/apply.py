"""Apply remote `ops` messages to the local scene, without echoing them back out (#6).

The receiving half of #5: `apply_message` is what #12's WebSocket client will call, on
Blender's main thread, for each message the relay forwards. No network yet.

Prototype limitation: `collab_id`s are assigned per Blender session (#4) from random
UUIDs, so an operation from one client only matches another's objects if both already
have the *same* IDs on the *same* objects. Until joining a room syncs state (#20), both
clients open the same saved `.blend` file first — see addon/README.md.

Last-writer-wins (#8 / #9): an incoming `set` is only applied if it's newer than the
last value this client sent or applied for that key, via the shared clock and `Versions`
in `ordering.py`.

Create / delete (#15): `create` builds a mesh object and `delete` removes one, both idempotent.
A deleted ID stays tombstoned (`ordering.tombstones`), so any later operation for it is
skipped whatever its timestamp: deletes win (protocol rule 2). A `set` for an object this
client doesn't have is dropped, not buffered (protocol rule 9).
"""

import bpy

from . import detect, ids, ordering, timing
from .log import log

# Fixed table (protocol rule 5): `property` is looked up here, never passed to `setattr`.


def _set_location(obj: bpy.types.Object, value: list) -> None:
    obj.location = value


def _set_scale(obj: bpy.types.Object, value: list) -> None:
    obj.scale = value


def _set_name(obj: bpy.types.Object, value: str) -> None:
    obj.name = value


def _set_rotation(obj: bpy.types.Object, value: dict) -> None:
    obj.rotation_mode = value["mode"]
    if value["mode"] == "QUATERNION":
        obj.rotation_quaternion = value["values"]
    elif value["mode"] == "AXIS_ANGLE":
        obj.rotation_axis_angle = value["values"]
    else:
        obj.rotation_euler = value["values"]


_SETTERS = {
    "location": _set_location,
    "scale": _set_scale,
    "rotation": _set_rotation,
    "name": _set_name,
}


def _target_collection(name: object) -> bpy.types.Collection:
    """The collection in this scene called `name`, or the scene's top level if there's none.
    Only this scene's: an object linked anywhere else wouldn't be in `scene.objects`."""
    scene = bpy.context.scene
    for collection in scene.collection.children_recursive:
        if collection.name == name:
            return collection
    return scene.collection


def _apply_create(op: dict, objects: dict[str, bpy.types.Object]) -> None:
    """Build the object `op` describes, unless it exists already or has been deleted."""
    collab_id = op.get("object")
    if collab_id in objects or collab_id in ordering.tombstones:
        log("apply: skip, create for existing or deleted object", collab_id)
        return
    if op.get("object_type") != "MESH":
        log("apply: skip, create for object type", op.get("object_type"))
        return

    mesh = None
    obj = None
    try:
        mesh = bpy.data.meshes.new(op["name"])
        mesh.from_pydata(op["mesh"]["vertices"], [], op["mesh"]["faces"])
        mesh.validate()  # untrusted geometry: the schema allows a face like [0, 0, 0]
        mesh.update()
        obj = bpy.data.objects.new(op["name"], mesh)
        for prop in ("location", "rotation", "scale"):
            _SETTERS[prop](obj, op["transform"][prop])
        obj[ids.COLLAB_ID] = collab_id
        _target_collection(op["collection"]).objects.link(obj)
    except Exception as exc:  # noqa: BLE001 - a malformed create must not crash the batch
        log("apply: skip, create raised", collab_id, exc)
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None:
            bpy.data.meshes.remove(mesh)
        return
    objects[collab_id] = obj
    timing.mark("applied", [op])


def _apply_delete(op: dict, objects: dict[str, bpy.types.Object]) -> None:
    """Tombstone the ID, even if this client never had the object (the `create` might still
    be on its way), then remove the object and any mesh left without users."""
    collab_id = op.get("object")
    ordering.tombstones.add(collab_id)
    obj = objects.pop(collab_id, None)
    if obj is None:
        return
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if isinstance(data, bpy.types.Mesh) and data.users == 0:
        bpy.data.meshes.remove(data)
    timing.mark("applied", [op])


def _apply_op(op: dict, objects: dict[str, bpy.types.Object], own_origin: str | None) -> None:
    """Apply one operation to `objects` (keyed by `collab_id`), or skip it and log why.

    Never raises: an unknown object / kind / property is skipped, and so is a `set` for a
    deleted object, a `set` that arrives older than the last value this client sent or applied
    for that (`object`, `property`) key (last-writer-wins, #8 / #9), or one whose setter itself
    raises (a value that's schema-valid JSON but not a value Blender accepts).
    """
    if not isinstance(op, dict):
        log("apply: skip, operation is not an object")
        return
    if op.get("origin") == own_origin:
        return  # the relay never echoes a client's own ops, but be defensive
    if not isinstance(op.get("object"), str):
        log("apply: skip, object ID is not a string")
        return
    kind = op.get("kind")
    if kind in ("create", "delete"):
        if isinstance(op.get("lamport"), int):
            ordering.clock.observe(op["lamport"])
        if kind == "create":
            _apply_create(op, objects)
        else:
            _apply_delete(op, objects)
        return
    if kind != "set":
        log("apply: skip, kind", kind)
        return
    if op.get("object") in ordering.tombstones:
        log("apply: skip, object was deleted", op.get("object"))
        return
    setter = _SETTERS.get(op.get("property"))
    if setter is None:
        log("apply: skip, unknown property", op.get("property"))
        return
    obj = objects.get(op.get("object"))
    if obj is None:
        log("apply: skip, unknown object", op.get("object"))
        return

    op_id = (op.get("lamport"), op.get("origin"))
    ordering.clock.observe(op_id[0])
    key = (op["object"], op["property"])
    if not ordering.versions.should_apply(key, op_id):
        log("apply: skip, older than local", op["object"], op["property"])
        return

    try:
        setter(obj, op["value"])
    except Exception as exc:  # noqa: BLE001 - a malformed value must not crash the batch
        log("apply: skip, setter raised", op["property"], exc)
        return

    ordering.versions.record(key, op_id)
    timing.mark("applied", [op])


def apply_message(message: dict) -> None:
    """Apply one parsed `ops` message to the local scene.

    `message` is a plain dict (parsed JSON), not a Pydantic model — the add-on can't use
    Pydantic. Runs the whole batch inside one `detect.suppressed()` block, which sends
    any pending local edit first and silently resyncs detect's cache on exit, so nothing
    applied here is echoed back out as if it were a local change (D-035, the #5 fix).
    """
    if not isinstance(message, dict) or message.get("v") != 1 or message.get("type") != "ops":
        log("apply: skip, not a v1 ops message")
        return
    ops = message.get("ops")
    if not isinstance(ops, list):
        log("apply: skip, ops is not a list")
        return

    # Look up objects once per batch, rather than ids.find_object per operation.
    objects: dict[str, bpy.types.Object] = {}
    for obj in bpy.context.scene.objects:
        collab_id = ids.get_id(obj)
        if collab_id is not None:
            objects[collab_id] = obj

    own_origin = detect.origin()
    with detect.suppressed():
        for op in ops:
            _apply_op(op, objects, own_origin)
