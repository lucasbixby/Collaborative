"""Tests for joining and leaving the session's room: wires detect, apply and client together.

Each test reads the add-on's modules off the `addon` fixture rather than importing them at
module level: the fixture re-imports the package for every test, so an import bound once at
collection time would stop matching what the registered operators call.
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


def _session(addon, relay=None, room="room-a", **values):
    url = f"ws://localhost:{relay.port}" if relay else "ws://localhost:1"
    return addon.session.configure(server_url=url, room=room, **values)


def test_join_connects_starts_detection_and_a_moved_object_reaches_the_relay(addon, relay):
    obj = _add_cube()
    _settle()
    _session(addon, relay, token="t0k")

    result = bpy.ops.collaborative.join_room()

    assert result == {"FINISHED"}
    wait_until(lambda: addon.client.status() == "connected")
    assert addon.detect._active
    assert relay.authorizations == ["Bearer t0k"]

    obj.location = (1.0, 2.0, 3.0)
    _settle()
    addon.detect.flush()

    wait_until(lambda: len(relay.received) >= 1)
    op = json.loads(relay.received[-1])["ops"][0]
    assert (op["property"], op["value"]) == ("location", [1.0, 2.0, 3.0])


def test_the_app_launching_blender_into_a_room_joins_without_a_click(addon, relay):
    _session(addon, relay)

    addon.operators.join_when_ready()
    assert bpy.app.timers.is_registered(addon.operators._auto_join)
    addon.operators._auto_join()  # what the timer runs once Blender has started

    wait_until(lambda: addon.client.status() == "connected")


def test_without_a_room_nothing_joins_and_the_button_is_off(addon):
    addon.session.configure()

    addon.operators.join_when_ready()

    assert not bpy.app.timers.is_registered(addon.operators._auto_join)
    assert not bpy.ops.collaborative.join_room.poll()


def test_invalid_room_name_cancels_and_nothing_starts(addon):
    _session(addon, room="bad room!")

    with pytest.raises(RuntimeError, match="invalid room id"):
        bpy.ops.collaborative.join_room()

    assert addon.client.status() == "disconnected"
    assert not addon.detect._active


def test_a_viewer_connects_but_sends_no_edits(addon, relay):
    obj = _add_cube()
    _settle()
    _session(addon, relay, role="viewer")

    bpy.ops.collaborative.join_room()
    wait_until(lambda: addon.client.status() == "connected")
    obj.location = (1.0, 2.0, 3.0)
    _settle()
    addon.detect.flush()

    assert not addon.detect._active
    assert relay.received == []


def test_leave_disconnects_and_stops_detection(addon, relay):
    _session(addon, relay)
    bpy.ops.collaborative.join_room()
    wait_until(lambda: addon.client.status() == "connected")

    result = bpy.ops.collaborative.leave_room()

    assert result == {"FINISHED"}
    assert addon.client.status() == "disconnected"
    assert not addon.detect._active


def test_join_while_detection_was_already_running_still_sends(addon, relay):
    # Join must not be a no-op just because a previous room left detection running.
    obj = _add_cube()
    _settle()
    addon.detect.start(lambda message: None)
    addon.detect.flush()  # enters the cache silently
    _session(addon, relay)

    bpy.ops.collaborative.join_room()
    wait_until(lambda: addon.client.status() == "connected")

    obj.location = (5.0, 5.0, 5.0)
    _settle()
    addon.detect.flush()

    wait_until(lambda: len(relay.received) >= 1)
    assert json.loads(relay.received[-1])["ops"][0]["value"] == [5.0, 5.0, 5.0]


def test_load_pre_leaves_the_room(addon, relay):
    _session(addon, relay)
    bpy.ops.collaborative.join_room()
    wait_until(lambda: addon.client.status() == "connected")

    assert addon.operators._on_load_pre in bpy.app.handlers.load_pre

    addon.operators._on_load_pre()

    assert addon.client.status() == "disconnected"
    assert not addon.detect._active


def test_load_pre_forgets_tombstones(addon):
    # They belong to the file being replaced: reopening the saved file brings deleted objects
    # back legitimately, under their old IDs.
    addon.ordering.tombstones.add("11111111-1111-1111-1111-111111111111")

    addon.operators._on_load_pre()

    assert addon.ordering.tombstones == set()


def test_status_text_for_each_state(addon):
    text = addon.panel._STATUS_TEXT
    assert text["disconnected"].format(room="demo") == "Not connected"
    assert text["connecting"].format(room="demo") == "Connecting to demo…"
    assert text["syncing"].format(room="demo") == "Catching up with demo…"
    assert text["connected"].format(room="demo") == "Connected to demo"
    assert text["reconnecting"].format(room="demo") == "Reconnecting to demo…"


@pytest.mark.parametrize(
    ("code", "shown"),
    [
        (4401, "Signed out: launch again from the Collaborative app"),
        (4403, "No access to room-a"),
    ],
)
def test_a_refusal_is_explained_in_the_panel(addon, relay, code, shown):
    relay.refuse_with = (code, "whatever the server said")
    _session(addon, relay)

    bpy.ops.collaborative.join_room()
    wait_until(lambda: addon.client.status() == "refused")

    assert addon.panel.status_text("room-a") == shown
    assert bpy.ops.collaborative.join_room.poll()  # Rejoin is how to try again
