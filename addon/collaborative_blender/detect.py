"""Detect local scene changes and turn them into `ops` messages (docs/protocol.md).

Blender's handlers only set a dirty flag; a ~50 ms timer does the work. When dirty, `flush()`
diffs every scene object against a cache keyed by `collab_id`: a changed property becomes a
`set`, an ID it hasn't seen a `create`, a missing ID a `delete`. One mechanism covers drags,
renames, undo and redo, adds and deletes, and nothing holds an object reference across undo.

Changes made by applying a remote operation go through `suppressed()`, so they aren't sent
back out as local edits. Timestamps come from the shared clock in ordering.py.

`start` snapshots the scene silently, so nothing already in it is sent on joining. Once the
room's catch-up is applied, `send_unknown_creates` offers the room each local mesh it doesn't
know. Edits made while not in a room are never sent.
"""

import json
import uuid
from contextlib import contextmanager

import bpy
from bpy.app.handlers import persistent

from . import ids, ordering, timing
from .log import log

INTERVAL = 0.05  # 50 ms
MAX_MESSAGE_BYTES = 64 * 1024  # the relay's limit (COLLAB_MAX_OPERATION_BYTES)
_ENVELOPE_BYTES = len('{"v": 1, "type": "ops", "ops": []}')
SCENE_COLLECTION = "Scene Collection"  # how protocol.md names the scene's top level
VERTEX_DECIMALS = 6  # keeps `create` messages small
_TRANSFORM_PROPERTIES = ("location", "rotation", "scale")
_TRACKED_PROPERTIES = (*_TRANSFORM_PROPERTIES, "name")

_active = False
_dirty = False
_suppress_depth = 0
_cache: dict[str, dict[str, object]] = {}
_origin: str | None = None
_send = None
_flush_started_at = None
_noticed_at = None  # for latency timing: when the scene first went dirty since the last flush


def _read_rotation(obj: bpy.types.Object) -> dict:
    """`{"mode", "values"}`, reading whichever rotation property matches the current mode."""
    mode = obj.rotation_mode
    if mode == "QUATERNION":
        values = tuple(obj.rotation_quaternion)
    elif mode == "AXIS_ANGLE":
        values = tuple(obj.rotation_axis_angle)
    else:
        values = tuple(obj.rotation_euler)
    return {"mode": mode, "values": values}


def _read_object(obj: bpy.types.Object) -> dict[str, object]:
    """The tracked property values for one object, as plain Python values (never live
    Blender `Vector`/`Euler` objects), so two reads of an unchanged property compare equal."""
    return {
        "location": tuple(obj.location),
        "rotation": _read_rotation(obj),
        "scale": tuple(obj.scale),
        "name": obj.name,
    }


def _snapshot() -> dict[str, dict[str, object]]:
    """Tracked values for every scene object, keyed by `collab_id`. Assigns IDs first,
    so a brand-new object is in the result even before it moves."""
    ids.ensure_ids()
    return {ids.get_id(obj): _read_object(obj) for obj in bpy.context.scene.objects}


def _op_value(prop: str, value: object) -> object:
    """`value` as JSON-ready data: lists, not the tuples the cache stores internally."""
    if prop == "rotation":
        return {"mode": value["mode"], "values": list(value["values"])}
    if prop == "name":
        return value
    return list(value)


def _make_op(collab_id: str, prop: str, value: object) -> dict:
    lamport = ordering.clock.tick()
    ordering.versions.record((collab_id, prop), (lamport, _origin))
    return {
        "kind": "set",
        "object": collab_id,
        "property": prop,
        "value": _op_value(prop, value),
        "lamport": lamport,
        "origin": _origin,
    }


def _make_delete_op(collab_id: str) -> dict:
    ordering.tombstones.add(collab_id)
    return {
        "kind": "delete",
        "object": collab_id,
        "lamport": ordering.clock.tick(),
        "origin": _origin,
    }


def _collection_name(obj: bpy.types.Object) -> str:
    collection = obj.users_collection[0]
    if collection == bpy.context.scene.collection:
        return SCENE_COLLECTION
    return collection.name


def _make_create_op(obj: bpy.types.Object, collab_id: str, values: dict[str, object]) -> dict:
    """Everything another client needs to rebuild `obj`. Reads the base mesh, not the
    evaluated one, since modifiers aren't synced.

    A `create` counts as a write of each property it carries, so it's recorded in `versions`
    like a `set`, and an older `set` for this object loses to it."""
    lamport = ordering.clock.tick()
    for prop in _TRACKED_PROPERTIES:
        ordering.versions.record((collab_id, prop), (lamport, _origin))
    return {
        "kind": "create",
        "object": collab_id,
        "lamport": lamport,
        "origin": _origin,
        "name": values["name"],
        "object_type": "MESH",
        "collection": _collection_name(obj),
        "transform": {prop: _op_value(prop, values[prop]) for prop in _TRANSFORM_PROPERTIES},
        "mesh": {
            "vertices": [
                [round(coordinate, VERTEX_DECIMALS) for coordinate in vertex.co]
                for vertex in obj.data.vertices
            ],
            "faces": [list(polygon.vertices) for polygon in obj.data.polygons],
        },
    }


def _send_create(obj: bpy.types.Object, collab_id: str, values: dict[str, object]) -> None:
    """Send a new object's `create` as its own message, or log why it can't be.

    Either way the object stays in the cache, so this runs once per object, not every flush.
    """
    if obj.type != "MESH":
        log("not synced yet:", obj.name, obj.type)
        return
    message = {"v": 1, "type": "ops", "ops": [_make_create_op(obj, collab_id, values)]}
    # Measured the way client.send serializes it, so this agrees with the relay's own check.
    size = len(json.dumps(message).encode("utf-8"))
    if size > MAX_MESSAGE_BYTES:
        log(f"too large to sync: {obj.name}, {size} bytes")
        return
    _send_timed(message)


def send_unknown_creates(known: set[str]) -> None:
    """Merge on join: send a `create` for each local object the room's catch-up didn't
    mention, so joining with a scene adds it to the room rather than hiding it.

    Called once per Join, after the catch-up has been applied, with every object ID it
    mentioned. Uses the normal create path, so non-mesh and oversized objects are only logged.
    """
    if not _active:
        return
    ids.ensure_ids()
    sent = 0
    for obj in bpy.context.scene.objects:
        collab_id = ids.get_id(obj)
        if collab_id in known or collab_id in ordering.tombstones:
            continue
        _send_create(obj, collab_id, _read_object(obj))
        sent += 1
    if sent:
        log(f"joined: offered {sent} local object(s) the room didn't have")


def _send_timed(message: dict) -> None:
    """Send `message`, first recording (for latency timing) when the change behind it was
    noticed and when this flush began: both are only known once the operations exist."""
    timing.mark("noticed", message["ops"], _noticed_at)
    timing.mark("flush_start", message["ops"], _flush_started_at)
    _send(message)


def _retire_tombstoned_ids() -> None:
    """Give a new ID to any object carrying a tombstoned one, which is how Cmd+Z brings a
    deleted object back. Every receiver ignores the old ID forever (protocol rule 2), so the
    object has to come back as a new one; it then isn't in the cache, so it gets a `create`."""
    for obj in bpy.context.scene.objects:
        collab_id = ids.get_id(obj)
        if collab_id in ordering.tombstones:
            ids.assign_new_id(obj)
            _cache.pop(collab_id, None)


def flush() -> dict | None:
    """If dirty, diff the scene against the cache and send the changes.

    Each `create` goes out as its own message, ahead of one batch of this flush's `set`s and
    `delete`s: a big mesh can't push the batch over the size limit, and a receiver always
    sees an object's `create` before any `set` for it.

    Returns this flush's `set`s and `delete`s as one message, or None if there were none (a
    flush that only sends `create`s returns None); on the wire they are split if they wouldn't
    fit in one. A plain function, not the timer callback itself, so headless tests can call it.
    """
    global _dirty, _cache, _flush_started_at, _noticed_at
    if not _dirty:
        return None
    _dirty = False
    _flush_started_at = timing.now()

    _retire_tombstoned_ids()
    current = _snapshot()
    objects = {ids.get_id(obj): obj for obj in bpy.context.scene.objects}
    ops = []
    for collab_id, values in current.items():
        previous = _cache.get(collab_id)
        if previous is None:
            _send_create(objects[collab_id], collab_id, values)
            continue
        for prop in _TRACKED_PROPERTIES:
            if values[prop] != previous[prop]:
                ops.append(_make_op(collab_id, prop, values[prop]))
    ops.extend(_make_delete_op(collab_id) for collab_id in _cache if collab_id not in current)
    _cache = current

    for batch in _batches(ops):
        _send_timed({"v": 1, "type": "ops", "ops": batch})
    _noticed_at = None
    return {"v": 1, "type": "ops", "ops": ops} if ops else None


def _batches(ops: list[dict]) -> list[list[dict]]:
    """Split `ops` into runs that each fit in one message. The relay rejects an oversized
    message whole, which would lose every change in it (deleting a few hundred objects at once
    is enough), while the order of the ops, which is all that matters, survives a split."""
    batches: list[list[dict]] = []
    size = MAX_MESSAGE_BYTES  # so the first op opens a batch
    for op in ops:
        cost = len(json.dumps(op).encode("utf-8")) + 2  # ", " between ops
        if size + cost > MAX_MESSAGE_BYTES:
            batches.append([])
            size = _ENVELOPE_BYTES
        batches[-1].append(op)
        size += cost
    return batches


def _mark_dirty(*_args) -> None:
    global _dirty, _noticed_at
    if _suppress_depth == 0:
        if not _dirty and _noticed_at is None:
            _noticed_at = timing.now()
        _dirty = True


@persistent
def _on_depsgraph_update(scene, depsgraph) -> None:
    _mark_dirty()


@persistent
def _on_undo_redo(scene) -> None:
    _mark_dirty()


# (handler list, handler function) pairs; same shape so start()/stop() can loop over them.
_HANDLERS = (
    (bpy.app.handlers.depsgraph_update_post, _on_depsgraph_update),
    (bpy.app.handlers.undo_post, _on_undo_redo),
    (bpy.app.handlers.redo_post, _on_undo_redo),
)


def _tick() -> float:
    flush()
    return INTERVAL  # reschedule; returning None would stop the timer


def start(send) -> None:
    """Start turning local edits into operations, delivered to `send` every ~50 ms.

    Takes a new client `origin`, then snapshots the scene so joining doesn't resend what's
    already in it. The Lamport clock is shared and never resets, so a restarted client's edits
    still outrank its own older ones. Does nothing if already started.
    """
    global _active, _send, _origin, _dirty, _cache
    if _active:
        return
    _active = True
    _send = send
    _origin = str(uuid.uuid4())
    _dirty = False
    _cache = _snapshot()
    for handler_list, handler in _HANDLERS:
        if handler not in handler_list:
            handler_list.append(handler)
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=INTERVAL, persistent=True)


def stop() -> None:
    """Stop detection: removes the handlers and the timer. Safe to call when not started."""
    global _active
    if not _active:
        return
    _active = False
    for handler_list, handler in _HANDLERS:
        if handler in handler_list:
            handler_list.remove(handler)
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)


def origin() -> str | None:
    """This client's own `origin` UUID, or None if detection hasn't started."""
    return _origin


@contextmanager
def suppressed():
    """Ignore changes made inside the block (used while applying a remote operation).

    Entering the outermost block flushes first: a local edit still waiting for its tick must
    go out before a remote operation is applied, or it would be absorbed into the cache on
    exit and never sent. On exit the cache is refreshed from the scene without sending, so
    what was applied here isn't diffed back out as a local edit.
    """
    global _suppress_depth, _cache, _dirty
    if _suppress_depth == 0:
        flush()
    _suppress_depth += 1
    try:
        yield
    finally:
        _suppress_depth -= 1
        if _suppress_depth == 0:
            _cache = _snapshot()
            _dirty = False
