"""Tests for applying remote operations without echo loops (#6)."""

import json
import re
from pathlib import Path

import bpy
import pytest

from collaborative_blender import apply, detect, ids

PROTOCOL_MD = Path(__file__).resolve().parents[2] / "docs" / "protocol.md"

REMOTE_ORIGIN = "11111111-1111-1111-1111-111111111111"
OTHER_REMOTE_ORIGIN = "22222222-2222-2222-2222-222222222222"


def _example_messages() -> list[dict]:
    """The example `ops` messages in docs/protocol.md, in the order they appear."""
    text = PROTOCOL_MD.read_text(encoding="utf-8")
    blocks = [json.loads(block) for block in re.findall(r"```json\n(.*?)```", text, re.DOTALL)]
    return [block for block in blocks if block.get("type") == "ops"]


EXAMPLES = _example_messages()


def _add_cube(name="Cube"):
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _settle():
    """Evaluate the depsgraph so a change made from a script reaches detect's handlers."""
    bpy.context.view_layer.update()


def _set_op(object_id, prop, value, *, lamport=1, origin=REMOTE_ORIGIN):
    return {
        "kind": "set",
        "object": object_id,
        "property": prop,
        "value": value,
        "lamport": lamport,
        "origin": origin,
    }


def _ops_message(*ops):
    return {"v": 1, "type": "ops", "ops": list(ops)}


@pytest.fixture
def sent(addon):
    """Messages passed to `send` while detection runs; always stopped afterwards."""
    messages = []
    detect.start(messages.append)
    yield messages
    detect.stop()


def test_applies_location(addon):
    obj = _add_cube()
    ids.ensure_ids()

    apply.apply_message(_ops_message(_set_op(ids.get_id(obj), "location", [1.0, 2.0, 3.0])))

    assert tuple(obj.location) == pytest.approx((1.0, 2.0, 3.0))


def test_applies_scale(addon):
    obj = _add_cube()
    ids.ensure_ids()

    apply.apply_message(_ops_message(_set_op(ids.get_id(obj), "scale", [2.0, 2.0, 2.0])))

    assert tuple(obj.scale) == pytest.approx((2.0, 2.0, 2.0))


def test_applies_euler_rotation(addon):
    obj = _add_cube()
    ids.ensure_ids()
    value = {"mode": "XYZ", "values": [0.0, 0.0, 1.5708]}

    apply.apply_message(_ops_message(_set_op(ids.get_id(obj), "rotation", value)))

    assert obj.rotation_mode == "XYZ"
    assert tuple(obj.rotation_euler) == pytest.approx((0.0, 0.0, 1.5708))


def test_applies_quaternion_rotation_including_mode_change(addon):
    obj = _add_cube()  # default rotation_mode is "XYZ"
    ids.ensure_ids()
    value = {"mode": "QUATERNION", "values": [0.7071068, 0.7071068, 0.0, 0.0]}

    apply.apply_message(_ops_message(_set_op(ids.get_id(obj), "rotation", value)))

    assert obj.rotation_mode == "QUATERNION"
    assert tuple(obj.rotation_quaternion) == pytest.approx((0.7071068, 0.7071068, 0.0, 0.0))


def test_applies_axis_angle_rotation(addon):
    obj = _add_cube()
    ids.ensure_ids()
    value = {"mode": "AXIS_ANGLE", "values": [1.5708, 0.0, 0.0, 1.0]}

    apply.apply_message(_ops_message(_set_op(ids.get_id(obj), "rotation", value)))

    assert obj.rotation_mode == "AXIS_ANGLE"
    assert tuple(obj.rotation_axis_angle) == pytest.approx((1.5708, 0.0, 0.0, 1.0))


def test_applies_name(addon):
    obj = _add_cube()
    ids.ensure_ids()

    apply.apply_message(_ops_message(_set_op(ids.get_id(obj), "name", "Box")))

    assert obj.name == "Box"


def test_unknown_object_id_is_skipped_rest_of_batch_still_applies(addon):
    obj = _add_cube()
    ids.ensure_ids()
    message = _ops_message(
        _set_op("00000000-0000-0000-0000-000000000000", "location", [9.0, 9.0, 9.0], lamport=1),
        _set_op(ids.get_id(obj), "location", [1.0, 2.0, 3.0], lamport=2),
    )

    apply.apply_message(message)  # must not raise

    assert tuple(obj.location) == pytest.approx((1.0, 2.0, 3.0))


def test_create_delete_unknown_kind_and_property_are_skipped_without_raising(addon):
    obj = _add_cube()
    ids.ensure_ids()
    collab_id = ids.get_id(obj)
    message = _ops_message(
        {"kind": "create", "object": "irrelevant", "lamport": 1, "origin": REMOTE_ORIGIN},
        {"kind": "delete", "object": "irrelevant", "lamport": 2, "origin": REMOTE_ORIGIN},
        {"kind": "frobnicate", "object": collab_id, "lamport": 3, "origin": REMOTE_ORIGIN},
        _set_op(collab_id, "glow_intensity", 11, lamport=4),
        _set_op(collab_id, "scale", [5.0, 5.0, 5.0], lamport=5),
    )

    apply.apply_message(message)  # must not raise

    assert tuple(obj.scale) == pytest.approx((5.0, 5.0, 5.0))  # the one valid op still applied


def test_malformed_messages_are_skipped_without_raising(addon):
    obj = _add_cube()
    ids.ensure_ids()
    good_op = _set_op(ids.get_id(obj), "location", [1.0, 1.0, 1.0])

    apply.apply_message({"v": 1, "type": "snapshot", "ops": [good_op]})
    apply.apply_message({"v": 2, "type": "ops", "ops": [good_op]})
    apply.apply_message({"type": "ops", "ops": [good_op]})  # missing v
    apply.apply_message({"v": 1, "type": "ops", "ops": "not-a-list"})
    apply.apply_message("not even a dict")
    apply.apply_message(None)

    assert tuple(obj.location) == pytest.approx((0.0, 0.0, 0.0))  # none of the above touched it


def test_own_origin_operations_are_skipped(sent):
    obj = _add_cube()
    _settle()
    detect.flush()  # enters the cache; detect.start() (via `sent`) set detect's origin

    op = _set_op(ids.get_id(obj), "location", [7.0, 7.0, 7.0], origin=detect.origin())
    apply.apply_message(_ops_message(op))

    assert tuple(obj.location) == pytest.approx((0.0, 0.0, 0.0))


def test_apply_then_flush_sends_nothing(sent):
    obj = _add_cube()
    _settle()
    detect.flush()  # enters the cache

    op = _set_op(ids.get_id(obj), "location", [4.0, 4.0, 4.0])
    apply.apply_message(_ops_message(op))

    assert tuple(obj.location) == pytest.approx((4.0, 4.0, 4.0))  # actually got applied
    assert detect.flush() is None  # but never diffed back out as a local change
    assert sent == []


def test_pending_local_edit_still_sent_when_remote_batch_applied(sent):
    # The #5 regression (D-038): a local edit still waiting for its 50 ms tick must be
    # sent before a remote operation is applied, not absorbed into the cache and lost.
    a = _add_cube("A")
    b = _add_cube("B")
    _settle()
    detect.flush()  # both enter the cache

    a.location = (5.0, 0.0, 0.0)  # local edit, not yet flushed
    _settle()

    remote_op = _set_op(ids.get_id(b), "location", [0.0, 7.0, 0.0])
    apply.apply_message(_ops_message(remote_op))

    assert detect.flush() is None  # B's remote change was absorbed silently, as designed
    assert len(sent) == 1
    op = sent[0]["ops"][0]
    assert op["object"] == ids.get_id(a)
    assert op["property"] == "location"
    assert op["value"] == [5.0, 0.0, 0.0]


def test_newer_incoming_op_is_applied(addon):
    obj = _add_cube()
    ids.ensure_ids()
    collab_id = ids.get_id(obj)

    apply.apply_message(
        _ops_message(_set_op(collab_id, "location", [1.0, 0.0, 0.0], lamport=1))
    )
    apply.apply_message(
        _ops_message(_set_op(collab_id, "location", [2.0, 0.0, 0.0], lamport=2))
    )

    assert tuple(obj.location) == pytest.approx((2.0, 0.0, 0.0))


def test_older_incoming_op_is_ignored_after_a_newer_local_edit(sent):
    # Detect's own emission records a version (D-044); an incoming op for the same key
    # must be checked against it too, not just against other incoming ops.
    obj = _add_cube()
    _settle()
    detect.flush()  # enters the cache

    obj.location = (1.0, 0.0, 0.0)
    _settle()
    local_message = detect.flush()
    local_lamport = local_message["ops"][0]["lamport"]

    older = _set_op(
        ids.get_id(obj),
        "location",
        [9.0, 9.0, 9.0],
        lamport=max(local_lamport - 1, 1),  # a lower lamport loses regardless of origin
        origin=REMOTE_ORIGIN,
    )
    apply.apply_message(_ops_message(older))

    assert tuple(obj.location) == pytest.approx((1.0, 0.0, 0.0))  # the local edit still stands


def test_equal_lamport_is_decided_by_origin(addon):
    obj = _add_cube()
    ids.ensure_ids()
    collab_id = ids.get_id(obj)

    # REMOTE_ORIGIN < OTHER_REMOTE_ORIGIN by string comparison.
    apply.apply_message(
        _ops_message(_set_op(collab_id, "location", [1.0, 0.0, 0.0], lamport=1, origin=REMOTE_ORIGIN))
    )
    apply.apply_message(
        _ops_message(
            _set_op(collab_id, "location", [2.0, 0.0, 0.0], lamport=1, origin=OTHER_REMOTE_ORIGIN)
        )
    )
    assert tuple(obj.location) == pytest.approx((2.0, 0.0, 0.0))  # larger origin wins the tie

    apply.apply_message(
        _ops_message(_set_op(collab_id, "location", [3.0, 0.0, 0.0], lamport=1, origin=REMOTE_ORIGIN))
    )
    assert tuple(obj.location) == pytest.approx((2.0, 0.0, 0.0))  # smaller origin still loses


def test_setter_exception_is_caught_and_the_rest_of_the_batch_still_applies(addon):
    obj = _add_cube()
    ids.ensure_ids()
    collab_id = ids.get_id(obj)
    message = _ops_message(
        _set_op(collab_id, "rotation", {"mode": "XYZ"}, lamport=1),  # missing "values"
        _set_op(collab_id, "scale", [3.0, 3.0, 3.0], lamport=2),
    )

    apply.apply_message(message)  # must not raise

    assert tuple(obj.scale) == pytest.approx((3.0, 3.0, 3.0))


def test_two_sets_of_the_same_property_in_a_batch_last_wins(addon):
    obj = _add_cube()
    ids.ensure_ids()
    message = _ops_message(
        _set_op(ids.get_id(obj), "location", [1.0, 0.0, 0.0], lamport=1),
        _set_op(ids.get_id(obj), "location", [2.0, 0.0, 0.0], lamport=2),
    )

    apply.apply_message(message)

    assert tuple(obj.location) == pytest.approx((2.0, 0.0, 0.0))


def test_every_protocol_example_is_accepted_without_raising(addon):
    for example in EXAMPLES:
        apply.apply_message(example)


def test_round_trip_reproduces_the_same_values(sent):
    obj = _add_cube()
    _settle()
    detect.flush()  # enters the cache

    obj.location = (1.0, 2.0, 3.0)
    obj.scale = (2.0, 2.0, 2.0)
    obj.rotation_euler = (0.0, 0.0, 1.5708)
    obj.name = "Box"
    _settle()
    message = detect.flush()
    for op in message["ops"]:
        # Simulate this batch having arrived from elsewhere: a different origin, and (so
        # it doesn't tie against the version detect's own emission just recorded for the
        # same key) a clearly higher lamport.
        op["origin"] = REMOTE_ORIGIN
        op["lamport"] += 1000

    # Reset to a blank slate, then apply exactly what detect sent for that change.
    obj.location = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.name = "Cube"

    apply.apply_message(message)

    assert tuple(obj.location) == pytest.approx((1.0, 2.0, 3.0))
    assert tuple(obj.scale) == pytest.approx((2.0, 2.0, 2.0))
    assert obj.rotation_mode == "XYZ"
    assert tuple(obj.rotation_euler) == pytest.approx((0.0, 0.0, 1.5708))
    assert obj.name == "Box"
