"""Tests for Join room / Leave room (#13): wires detect, apply and client together.

Each test imports `collaborative_blender.*` itself, after the `addon` fixture has
enabled the add-on, rather than at module level: `conftest.py`'s `addon` fixture drops
and re-imports the package fresh for every test, so an import bound once at collection
time would go stale after the first test and stop matching what the registered
operators actually call internally. `addon`'s own teardown (`unregister()`) already
calls `client.disconnect()` and `detect.stop()`, so no extra cleanup fixture is needed.
"""

import json

import bpy
import pytest
from conftest import wait_until


def _add_cube(name="Cube"):
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _settle():
    """Evaluate the depsgraph so a change made from a script reaches detect's handlers."""
    bpy.context.view_layer.update()


def _set_room(room_id: str, server_url: str) -> None:
    bpy.context.window_manager.room_id = room_id
    prefs = bpy.context.preferences.addons["collaborative_blender"].preferences
    prefs.server_url = server_url


def test_join_connects_starts_detection_and_a_moved_object_reaches_the_relay(addon, relay):
    obj = _add_cube()
    _settle()
    _set_room("room-a", f"ws://localhost:{relay.port}")

    result = bpy.ops.collaborative.join_room()

    assert result == {"FINISHED"}
    wait_until(lambda: addon.client.status() == "connected")
    assert addon.detect._active

    obj.location = (1.0, 2.0, 3.0)
    _settle()
    addon.detect.flush()

    wait_until(lambda: len(relay.received) >= 1)
    message = json.loads(relay.received[-1])
    op = message["ops"][0]
    assert op["property"] == "location"
    assert op["value"] == [1.0, 2.0, 3.0]


def test_invalid_room_id_cancels_and_nothing_starts(addon):
    _set_room("bad room!", "ws://localhost:1")

    with pytest.raises(RuntimeError, match="invalid room id"):
        bpy.ops.collaborative.join_room()

    assert addon.client.status() == "disconnected"
    assert not addon.detect._active


def test_leave_disconnects_and_stops_detection(addon, relay):
    _set_room("room-a", f"ws://localhost:{relay.port}")
    bpy.ops.collaborative.join_room()
    wait_until(lambda: addon.client.status() == "connected")

    result = bpy.ops.collaborative.leave_room()

    assert result == {"FINISHED"}
    assert addon.client.status() == "disconnected"
    assert not addon.detect._active


def test_join_while_detection_was_already_running_still_sends(addon, relay):
    # The #12 manual-check trap: Join must not be a no-op just because the old
    # Start detection dev aid (or a previous room) left detection running.
    obj = _add_cube()
    _settle()
    addon.detect.start(lambda message: None)
    addon.detect.flush()  # enters the cache silently
    _set_room("room-a", f"ws://localhost:{relay.port}")

    bpy.ops.collaborative.join_room()
    wait_until(lambda: addon.client.status() == "connected")

    obj.location = (5.0, 5.0, 5.0)
    _settle()
    addon.detect.flush()

    wait_until(lambda: len(relay.received) >= 1)
    message = json.loads(relay.received[-1])
    assert message["ops"][0]["value"] == [5.0, 5.0, 5.0]


def test_load_pre_leaves_the_room(addon, relay):
    _set_room("room-a", f"ws://localhost:{relay.port}")
    bpy.ops.collaborative.join_room()
    wait_until(lambda: addon.client.status() == "connected")

    assert addon.operators._on_load_pre in bpy.app.handlers.load_pre

    addon.operators._on_load_pre()

    assert addon.client.status() == "disconnected"
    assert not addon.detect._active


def test_status_text_for_each_state():
    from collaborative_blender import panel

    assert panel._STATUS_TEXT["disconnected"].format(room="demo") == "Not connected"
    assert panel._STATUS_TEXT["connecting"].format(room="demo") == "Connecting to demo…"
    assert panel._STATUS_TEXT["connected"].format(room="demo") == "Connected to demo"
    assert panel._STATUS_TEXT["reconnecting"].format(room="demo") == "Reconnecting to demo…"
