"""Tests for the out-of-band latency timing (#24)."""

import json

import bpy
import pytest
from conftest import wait_until

STAGES_ON_THE_WAY_OUT = {"noticed", "flush_start", "queued", "dequeued", "sent"}


@pytest.fixture
def timing(addon, tmp_path):
    """Timing on, writing to a temporary file, for the add-on as enabled for this test."""
    from collaborative_blender import timing as module

    path = tmp_path / "timing.jsonl"
    module.configure(str(path), source="A")
    yield module, path
    module.configure(None)


def _lines(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def _op(lamport=1) -> dict:
    return {"kind": "set", "object": "obj", "origin": "me", "lamport": lamport}


def test_off_by_default_writes_nothing_and_reads_no_clock(addon, tmp_path, monkeypatch):
    from collaborative_blender import timing as module

    module.configure(None)
    monkeypatch.chdir(tmp_path)

    assert module.enabled() is False
    assert module.now() is None
    module.mark("noticed", [_op()])
    module.flush()

    assert len(module._buffer) == 0
    assert list(tmp_path.iterdir()) == []


def test_on_writes_one_well_formed_line_per_op(timing):
    module, path = timing

    module.mark("noticed", [_op(1), _op(2)])
    module.flush()

    first, second = _lines(path)
    assert first["stage"] == "noticed"
    assert first["source"] == "A"
    assert (first["origin"], first["lamport"], first["object"]) == ("me", 1, "obj")
    assert first["kind"] == "set"
    assert isinstance(first["mono_ns"], int) and isinstance(first["wall_ns"], int)
    assert second["lamport"] == 2


def test_raw_message_text_is_keyed_too(timing):
    module, path = timing

    module.mark("sent", json.dumps({"v": 1, "type": "ops", "ops": [_op(7)]}))
    module.flush()

    assert _lines(path)[0]["lamport"] == 7


def test_text_that_is_not_an_ops_message_is_skipped(timing):
    module, path = timing

    module.mark("received", "not json")
    module.mark("received", json.dumps({"v": 1, "type": "error", "message": "no"}))
    module.mark("received", json.dumps({"v": 1, "type": "ops", "ops": [{"kind": "set"}]}))
    module.flush()

    assert not path.exists() or _lines(path) == []


def test_mark_uses_an_earlier_time_when_given_one(timing):
    module, path = timing

    module.mark("noticed", [_op()], (5, 6))
    module.flush()

    assert (_lines(path)[0]["mono_ns"], _lines(path)[0]["wall_ns"]) == (5, 6)


def test_a_real_edit_records_the_sending_stages_in_order(addon, timing, relay):
    module, path = timing
    obj = bpy.data.objects.new("Cube", bpy.data.meshes.new("Cube"))
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    bpy.context.window_manager.room_id = "room-a"
    bpy.context.preferences.addons["collaborative_blender"].preferences.server_url = (
        f"ws://localhost:{relay.port}"
    )
    bpy.ops.collaborative.join_room()
    wait_until(lambda: addon.client.status() == "connected")

    obj.location = (1.0, 2.0, 3.0)
    bpy.context.view_layer.update()
    addon.detect.flush()
    wait_until(lambda: len(relay.received) >= 1)
    wait_until(lambda: any(stage == "sent" for stage, *_ in module._buffer) or path.exists())
    module.flush()

    times = {line["stage"]: line["mono_ns"] for line in _lines(path)}
    assert set(times) == STAGES_ON_THE_WAY_OUT
    assert (
        times["noticed"]
        <= times["flush_start"]
        <= times["queued"]
        <= times["dequeued"]
        <= times["sent"]
    )


def test_an_applied_op_is_marked_and_a_skipped_one_is_not(addon, timing):
    module, path = timing
    obj = bpy.data.objects.new("Cube", bpy.data.meshes.new("Cube"))
    bpy.context.scene.collection.objects.link(obj)
    collab_id = addon.ids.assign_new_id(obj)

    def message(object_id):
        op = {
            "kind": "set",
            "object": object_id,
            "property": "location",
            "value": [1.0, 2.0, 3.0],
            "lamport": 5,
            "origin": "someone",
        }
        return {"v": 1, "type": "ops", "ops": [op]}

    addon.apply.apply_message(message(collab_id))
    addon.apply.apply_message(message("unknown-object"))
    module.flush()

    assert [line["object"] for line in _lines(path) if line["stage"] == "applied"] == [collab_id]
