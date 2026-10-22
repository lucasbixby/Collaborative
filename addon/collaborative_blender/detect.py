"""Detect local scene changes and turn them into `ops` messages (docs/protocol.md, #5).

Design (issue #5): handlers only set a dirty flag; a ~50 ms timer does the real work. When
dirty, `flush()` calls `ids.ensure_ids()`, then diffs every scene object against a cache
keyed by `collab_id`, turns each changed property into a `set` operation, and sends the
batch. One mechanism covers drags, renames, undo/redo and new objects, since nothing holds
object references across undo (D-018 to D-021).

Changes caused by applying a remote operation go through `suppressed()` (see apply.py, #6)
to avoid echoing them back out as if they were local edits. Each emitted op's Lamport
timestamp comes from the shared clock in `ordering.py` (#8), not a counter of its own.
"""

import uuid
from contextlib import contextmanager

import bpy
from bpy.app.handlers import persistent

from . import ids, ordering

INTERVAL = 0.05  # 50 ms (D-019)
_TRACKED_PROPERTIES = ("location", "rotation", "scale", "name")

_active = False
_dirty = False
_suppress_depth = 0
_cache: dict[str, dict[str, object]] = {}
_origin: str | None = None
_send = None


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
    so a brand-new object is in the result (and enters the cache) even before it moves."""
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


def flush() -> dict | None:
    """If dirty, diff the scene against the cache and send any changes as one `ops` batch.

    Returns the message that was sent, or None if nothing changed. A plain function (not
    the timer callback itself), so headless tests can call it directly; `bpy.app.timers`
    don't run without Blender's own event loop.
    """
    global _dirty, _cache
    if not _dirty:
        return None
    _dirty = False

    current = _snapshot()
    ops = []
    for collab_id, values in current.items():
        previous = _cache.get(collab_id)
        if previous is None:
            continue  # a new object enters the cache silently; #15 sends `create` for it
        for prop in _TRACKED_PROPERTIES:
            if values[prop] != previous[prop]:
                ops.append(_make_op(collab_id, prop, values[prop]))
    _cache = current

    if not ops:
        return None
    message = {"v": 1, "type": "ops", "ops": ops}
    _send(message)
    return message


def _mark_dirty(*_args) -> None:
    global _dirty
    if _suppress_depth == 0:
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

    Generates a new client `origin` (D-025), then snapshots the current scene so joining
    a room doesn't resend everything already in it. The Lamport clock is shared and never
    resets (D-046), so a restarted client's edits still outrank its own older ones. Calling
    this again while already started does nothing, so it's safe to call more than once.
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


def is_active() -> bool:
    """Whether detection is currently running (for the panel's Start/Stop button)."""
    return _active


def origin() -> str | None:
    """This client's own `origin` UUID (None if detection hasn't started). Lets apply.py
    (#6) defensively skip an incoming operation that is somehow this client's own."""
    return _origin


@contextmanager
def suppressed():
    """Ignore changes made inside the block (used while applying a remote operation, #6).

    Entering the outermost `suppressed()` flushes first: a local edit still waiting for
    its 50 ms tick must be sent before a remote operation is applied, or it would be
    absorbed into the cache on exit and never sent at all.

    On exit the cache is refreshed from the scene without emitting anything, so a change
    applied here is never diffed back out on the next flush as if it were a local edit.
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
