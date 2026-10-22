"""Apply remote `ops` messages to the local scene, without echoing them back out (#6).

The receiving half of #5: `apply_message` is what #12's WebSocket client will call, on
Blender's main thread, for each message the relay forwards. No network yet.

Prototype limitation: `collab_id`s are assigned per Blender session (#4) from random
UUIDs, so an operation from one client only matches another's objects if both already
have the *same* IDs on the *same* objects. Until joining a room syncs state (#20), both
clients open the same saved `.blend` file first — see addon/README.md.
"""

import bpy

from . import detect, ids
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


def _apply_op(op: dict, objects: dict[str, bpy.types.Object], own_origin: str | None) -> None:
    """Apply one operation to `objects` (keyed by `collab_id`), or skip it and log why.

    Never raises. Ordering and conflicts (#8 / #9) will add a check here before the
    setter runs; kept as a single function so that slots in without restructuring the
    caller.
    """
    if not isinstance(op, dict):
        log("apply: skip, operation is not an object")
        return
    if op.get("origin") == own_origin:
        return  # the relay never echoes a client's own ops, but be defensive
    if op.get("kind") != "set":
        log("apply: skip, kind", op.get("kind"))  # create / delete are #15
        return
    setter = _SETTERS.get(op.get("property"))
    if setter is None:
        log("apply: skip, unknown property", op.get("property"))
        return
    obj = objects.get(op.get("object"))
    if obj is None:
        log("apply: skip, unknown object", op.get("object"))
        return
    setter(obj, op["value"])


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
