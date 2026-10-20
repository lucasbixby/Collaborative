"""Tests for change detection (#5): dirty flag + full diff, turned into `ops` messages."""

import json
import re
from pathlib import Path

import bpy
import jsonschema
import pytest

from collaborative_blender import detect, ids

PROTOCOL_MD = Path(__file__).resolve().parents[2] / "docs" / "protocol.md"


def _schema() -> dict:
    """The `ops` message JSON Schema embedded in docs/protocol.md."""
    text = PROTOCOL_MD.read_text(encoding="utf-8")
    blocks = [json.loads(block) for block in re.findall(r"```json\n(.*?)```", text, re.DOTALL)]
    return next(block for block in blocks if "$schema" in block)


SCHEMA = _schema()


def _add_cube(name="Cube"):
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _settle():
    """Evaluate the depsgraph so a change made from a script reaches detect's handlers."""
    bpy.context.view_layer.update()


def _only_op(message, prop):
    ops = [op for op in message["ops"] if op["property"] == prop]
    assert len(ops) == 1
    return ops[0]


@pytest.fixture
def sent(addon):
    """Messages passed to `send` while detection runs; always stopped afterwards."""
    messages = []
    detect.start(messages.append)
    yield messages
    detect.stop()


def test_move_emits_one_set_location(sent):
    obj = _add_cube()
    _settle()
    detect.flush()  # new object: enters the cache silently (no `create` op, #15)

    obj.location = (1.0, 2.0, 3.0)
    _settle()
    message = detect.flush()

    assert message["ops"] == [_only_op(message, "location")]
    op = message["ops"][0]
    assert op["kind"] == "set"
    assert op["object"] == ids.get_id(obj)
    assert op["value"] == [1.0, 2.0, 3.0]
    assert sent == [message]


def test_setting_the_same_value_emits_nothing(sent):
    obj = _add_cube()
    _settle()
    detect.flush()

    obj.location = tuple(obj.location)  # a write, but not an actual change
    _settle()

    assert detect.flush() is None
    assert sent == []


def test_several_moves_before_one_flush_give_a_single_op(sent):
    obj = _add_cube()
    _settle()
    detect.flush()

    obj.location = (1.0, 0.0, 0.0)
    _settle()
    obj.location = (2.0, 0.0, 0.0)
    _settle()
    obj.location = (3.0, 0.0, 0.0)
    _settle()

    message = detect.flush()

    op = _only_op(message, "location")
    assert op["value"] == [3.0, 0.0, 0.0]


def test_rotation_set_as_euler(sent):
    obj = _add_cube()
    _settle()
    detect.flush()

    obj.rotation_euler = (0.0, 0.0, 1.5708)
    _settle()

    op = _only_op(detect.flush(), "rotation")
    assert op["value"]["mode"] == "XYZ"
    assert op["value"]["values"] == pytest.approx([0.0, 0.0, 1.5708])


def test_rotation_set_as_quaternion(sent):
    obj = _add_cube()
    _settle()
    detect.flush()

    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = (0.7071068, 0.7071068, 0.0, 0.0)
    _settle()

    op = _only_op(detect.flush(), "rotation")
    assert op["value"]["mode"] == "QUATERNION"
    assert op["value"]["values"] == pytest.approx([0.7071068, 0.7071068, 0.0, 0.0])


def test_rotation_set_as_axis_angle(sent):
    obj = _add_cube()
    _settle()
    detect.flush()

    obj.rotation_mode = "AXIS_ANGLE"
    obj.rotation_axis_angle = (1.5708, 0.0, 0.0, 1.0)
    _settle()

    op = _only_op(detect.flush(), "rotation")
    assert op["value"]["mode"] == "AXIS_ANGLE"
    assert op["value"]["values"] == pytest.approx([1.5708, 0.0, 0.0, 1.0])


def test_scale_change_emits_set_scale(sent):
    obj = _add_cube()
    _settle()
    detect.flush()

    obj.scale = (2.0, 2.0, 2.0)
    _settle()

    op = _only_op(detect.flush(), "scale")
    assert op["value"] == [2.0, 2.0, 2.0]


def test_rename_emits_set_name(sent):
    obj = _add_cube()
    _settle()
    detect.flush()

    obj.name = "Box"
    _settle()

    op = _only_op(detect.flush(), "name")
    assert op["value"] == "Box"


def test_custom_property_change_emits_nothing(sent):
    obj = _add_cube()
    _settle()
    detect.flush()

    obj["some_flag"] = 1
    _settle()

    assert detect.flush() is None
    assert sent == []


def test_new_object_gets_an_id_and_later_moves_emit_ops(sent):
    obj = _add_cube()
    _settle()

    assert detect.flush() is None  # enters the cache silently
    collab_id = ids.get_id(obj)
    assert collab_id is not None

    obj.location = (5.0, 5.0, 5.0)
    _settle()
    message = detect.flush()

    op = _only_op(message, "location")
    assert op["object"] == collab_id
    assert op["value"] == [5.0, 5.0, 5.0]


def test_deleted_object_leaves_the_cache_without_errors(sent):
    obj = _add_cube()
    _settle()
    detect.flush()

    bpy.data.objects.remove(obj)
    _settle()

    assert detect.flush() is None  # no `delete` op (out of scope, #15); just drops silently


def test_changes_inside_suppressed_emit_nothing(sent):
    obj = _add_cube()
    _settle()
    detect.flush()
    collab_id = ids.get_id(obj)

    with detect.suppressed():
        obj.location = (9.0, 9.0, 9.0)
        _settle()

    assert detect.flush() is None
    assert sent == []
    # the cache was refreshed on exit, without emitting, so it already matches the scene
    assert detect._cache[collab_id]["location"] == (9.0, 9.0, 9.0)


def test_lamport_increases_and_origin_stays_fixed(sent):
    obj = _add_cube()
    _settle()
    detect.flush()

    obj.location = (1.0, 0.0, 0.0)
    _settle()
    first = detect.flush()

    obj.location = (2.0, 0.0, 0.0)
    obj.scale = (2.0, 2.0, 2.0)
    _settle()
    second = detect.flush()

    assert first["ops"][0]["origin"] == second["ops"][0]["origin"]
    assert second["ops"][0]["lamport"] > first["ops"][0]["lamport"]
    assert len(second["ops"]) == 2
    assert second["ops"][1]["lamport"] > second["ops"][0]["lamport"]


def test_start_twice_registers_one_handler(addon):
    detect.start(lambda message: None)
    detect.start(lambda message: None)

    assert bpy.app.handlers.depsgraph_update_post.count(detect._on_depsgraph_update) == 1

    detect.stop()


def test_stop_removes_handlers_and_timer(addon):
    detect.start(lambda message: None)

    detect.stop()

    assert detect._on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post
    assert detect._on_undo_redo not in bpy.app.handlers.undo_post
    assert detect._on_undo_redo not in bpy.app.handlers.redo_post
    assert not bpy.app.timers.is_registered(detect._tick)


def test_emitted_messages_match_the_protocol_schema(sent):
    obj = _add_cube()
    _settle()
    detect.flush()

    mutations = [
        lambda: setattr(obj, "location", (1.0, 2.0, 3.0)),
        lambda: setattr(obj, "scale", (2.0, 2.0, 2.0)),
        lambda: setattr(obj, "rotation_euler", (0.0, 0.0, 1.5708)),
        lambda: setattr(obj, "name", "Box"),
    ]
    for mutate in mutations:
        mutate()
        _settle()
        message = detect.flush()
        assert message is not None
        jsonschema.validate(instance=message, schema=SCHEMA)

    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = (0.7071068, 0.7071068, 0.0, 0.0)
    _settle()
    jsonschema.validate(instance=detect.flush(), schema=SCHEMA)

    obj.rotation_mode = "AXIS_ANGLE"
    obj.rotation_axis_angle = (1.5708, 0.0, 0.0, 1.0)
    _settle()
    jsonschema.validate(instance=detect.flush(), schema=SCHEMA)
