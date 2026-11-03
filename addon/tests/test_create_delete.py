"""Tests for syncing object creation and deletion (#15): detect emits, apply rebuilds."""

import itertools
import json
import re
import uuid
from pathlib import Path

import bpy
import jsonschema
import pytest

from collaborative_blender import apply, detect, ids, ordering

PROTOCOL_MD = Path(__file__).resolve().parents[2] / "docs" / "protocol.md"
REMOTE_ORIGIN = "11111111-1111-1111-1111-111111111111"

CUBE_VERTICES = [
    (1, 1, 1),
    (1, 1, -1),
    (1, -1, 1),
    (1, -1, -1),
    (-1, 1, 1),
    (-1, 1, -1),
    (-1, -1, 1),
    (-1, -1, -1),
]
CUBE_FACES = [
    (0, 4, 6, 2),
    (3, 2, 6, 7),
    (7, 6, 4, 5),
    (5, 1, 3, 7),
    (1, 0, 2, 3),
    (5, 4, 0, 1),
]


def _schema() -> dict:
    """The `ops` message JSON Schema embedded in docs/protocol.md."""
    text = PROTOCOL_MD.read_text(encoding="utf-8")
    blocks = [json.loads(block) for block in re.findall(r"```json\n(.*?)```", text, re.DOTALL)]
    return next(block for block in blocks if "$schema" in block)


SCHEMA = _schema()


def _add_cube(name="Cube", collection=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(CUBE_VERTICES, [], CUBE_FACES)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def _add_grid(vertex_count):
    """A mesh with `vertex_count` loose vertices, for testing the size limit."""
    mesh = bpy.data.meshes.new("Big")
    mesh.from_pydata([(i * 0.123456, 0.654321, 0.111111) for i in range(vertex_count)], [], [])
    mesh.update()
    obj = bpy.data.objects.new("Big", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _settle():
    """Evaluate the depsgraph so a change made from a script reaches detect's handlers."""
    bpy.context.view_layer.update()


def _settle_and_flush():
    _settle()
    return detect.flush()


def _ops(messages, kind):
    return [op for message in messages for op in message["ops"] if op["kind"] == kind]


def _new_id():
    return str(uuid.uuid4())


def _create_op(collab_id=None, *, lamport=1, origin=REMOTE_ORIGIN, **fields):
    return {
        "kind": "create",
        "object": collab_id or _new_id(),
        "lamport": lamport,
        "origin": origin,
        "name": "Cube",
        "object_type": "MESH",
        "collection": "Scene Collection",
        "transform": {
            "location": [1.0, 2.0, 3.0],
            "rotation": {"mode": "XYZ", "values": [0.0, 0.0, 1.5]},
            "scale": [2.0, 2.0, 2.0],
        },
        "mesh": {
            "vertices": [list(vertex) for vertex in CUBE_VERTICES],
            "faces": [list(face) for face in CUBE_FACES],
        },
        **fields,
    }


def _delete_op(collab_id, *, lamport=2, origin=REMOTE_ORIGIN):
    return {"kind": "delete", "object": collab_id, "lamport": lamport, "origin": origin}


def _location_op(collab_id, value, *, lamport=3, origin=REMOTE_ORIGIN):
    return {
        "kind": "set",
        "object": collab_id,
        "property": "location",
        "value": value,
        "lamport": lamport,
        "origin": origin,
    }


def _receive(*ops):
    apply.apply_message({"v": 1, "type": "ops", "ops": list(ops)})


@pytest.fixture
def sent(addon):
    """Messages passed to `send` while detection runs; always stopped afterwards."""
    messages = []
    detect.start(messages.append)
    yield messages
    detect.stop()


# -- Sending ------------------------------------------------------------------------------


def test_add_emits_a_create_matching_the_object(sent):
    obj = _add_cube()
    obj.location = (1.0, 2.0, 3.0)
    obj.scale = (2.0, 2.0, 2.0)
    obj.rotation_euler = (0.0, 0.0, 1.5)

    _settle_and_flush()

    assert len(sent) == 1
    jsonschema.validate(instance=sent[0], schema=SCHEMA)
    op = sent[0]["ops"][0]
    assert op["kind"] == "create"
    assert op["object"] == ids.get_id(obj)
    assert op["origin"] == detect.origin()
    assert op["name"] == "Cube"
    assert op["object_type"] == "MESH"
    assert op["collection"] == "Scene Collection"
    assert op["transform"]["location"] == [1.0, 2.0, 3.0]
    assert op["transform"]["scale"] == [2.0, 2.0, 2.0]
    assert op["transform"]["rotation"]["mode"] == "XYZ"
    assert op["mesh"]["vertices"] == [list(vertex) for vertex in CUBE_VERTICES]
    assert op["mesh"]["faces"] == [list(face) for face in CUBE_FACES]


def test_create_names_the_objects_collection(sent):
    collection = bpy.data.collections.new("Props")
    bpy.context.scene.collection.children.link(collection)
    _add_cube(collection=collection)

    _settle_and_flush()

    assert sent[0]["ops"][0]["collection"] == "Props"


def test_create_rounds_vertices_to_six_decimals(sent):
    mesh = bpy.data.meshes.new("Tri")
    mesh.from_pydata([(0.1234567891, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new("Tri", mesh)
    bpy.context.scene.collection.objects.link(obj)

    _settle_and_flush()

    assert sent[0]["ops"][0]["mesh"]["vertices"][0][0] == 0.123457


def test_create_reads_the_base_mesh_not_the_evaluated_one(sent):
    obj = _add_cube()
    obj.modifiers.new("Subdivide", "SUBSURF")

    _settle_and_flush()

    assert len(sent[0]["ops"][0]["mesh"]["vertices"]) == len(CUBE_VERTICES)


@pytest.mark.parametrize("linked", [False, True], ids=["shift-d", "alt-d"])
def test_duplicate_emits_a_create_with_a_new_id(sent, linked):
    # obj.copy() is what both Shift+D and Alt+D come down to; Alt+D shares the mesh.
    original = _add_cube()
    _settle_and_flush()
    sent.clear()

    copy = original.copy()
    if not linked:
        copy.data = original.data.copy()
    bpy.context.scene.collection.objects.link(copy)
    _settle_and_flush()

    assert len(sent) == 1
    jsonschema.validate(instance=sent[0], schema=SCHEMA)
    op = sent[0]["ops"][0]
    assert op["kind"] == "create"
    assert op["object"] == ids.get_id(copy)
    assert op["object"] != ids.get_id(original)


def test_delete_emits_a_delete_and_records_a_tombstone(sent):
    obj = _add_cube()
    _settle_and_flush()
    collab_id = ids.get_id(obj)
    sent.clear()

    bpy.data.objects.remove(obj)
    message = _settle_and_flush()

    assert message == sent[0]
    jsonschema.validate(instance=message, schema=SCHEMA)
    assert [op["kind"] for op in message["ops"]] == ["delete"]
    assert message["ops"][0]["object"] == collab_id
    assert collab_id in ordering.tombstones
    assert _settle_and_flush() is None  # only sent once


def test_a_new_non_mesh_object_emits_nothing_and_is_logged_once(sent, capsys):
    bpy.context.scene.collection.objects.link(bpy.data.objects.new("Empty", None))

    _settle_and_flush()
    detect._mark_dirty()
    _settle_and_flush()

    assert sent == []
    assert capsys.readouterr().out.count("not synced yet") == 1


def test_oversized_mesh_is_skipped_logged_once_and_stays_in_the_cache(sent, capsys):
    obj = _add_grid(5000)

    _settle_and_flush()
    detect._mark_dirty()
    _settle_and_flush()

    assert sent == []
    assert capsys.readouterr().out.count("too large to sync (#27)") == 1
    assert ids.get_id(obj) in detect._cache


def test_mesh_just_under_the_limit_is_sent(sent):
    # About 45 bytes per vertex, so this comes well inside 64 KiB.
    _add_grid(1000)

    _settle_and_flush()

    assert len(json.dumps(sent[0])) <= detect.MAX_MESSAGE_BYTES
    assert len(sent[0]["ops"][0]["mesh"]["vertices"]) == 1000


def test_each_create_is_its_own_message_ahead_of_the_batch(sent):
    existing = _add_cube("Existing")
    gone = _add_cube("Gone")
    _settle_and_flush()
    sent.clear()

    existing.location = (9.0, 0.0, 0.0)
    bpy.data.objects.remove(gone)
    _add_cube("New1")
    _add_cube("New2")
    batch = _settle_and_flush()

    assert [[op["kind"] for op in message["ops"]] for message in sent] == [
        ["create"],
        ["create"],
        ["set", "delete"],
    ]
    assert batch == sent[-1]


def test_objects_already_in_the_scene_on_join_emit_nothing(addon):
    _add_cube()
    messages = []
    detect.start(messages.append)

    _settle_and_flush()
    detect.stop()

    assert messages == []


def test_delete_then_undo_comes_back_as_a_create_with_a_new_id(sent):
    bpy.ops.mesh.primitive_cube_add()
    _settle_and_flush()  # assigns the ID, which the next undo step then captures
    old_id = ids.get_id(bpy.context.active_object)
    bpy.ops.ed.undo_push(message="add")
    bpy.ops.object.delete()
    bpy.ops.ed.undo_push(message="delete")
    _settle_and_flush()
    assert ids.find_object(old_id) is None
    sent.clear()

    bpy.ops.ed.undo()
    _settle_and_flush()

    assert len(sent) == 1  # a create only, and no second delete for the old ID
    jsonschema.validate(instance=sent[0], schema=SCHEMA)
    op = sent[0]["ops"][0]
    assert op["kind"] == "create"
    assert op["object"] != old_id
    assert ids.get_id(bpy.context.active_object) == op["object"]
    assert old_id in ordering.tombstones


def test_object_undeleted_while_out_of_the_room_comes_back_on_the_next_change(addon):
    # Join's snapshot is silent, so it picks up the old ID; the first flush then retires it.
    old_id = _new_id()
    ordering.tombstones.add(old_id)
    restored = _add_cube()
    restored[ids.COLLAB_ID] = old_id
    messages = []
    detect.start(messages.append)

    restored.location = (1.0, 0.0, 0.0)
    _settle_and_flush()
    detect.stop()

    assert len(messages) == 1
    assert messages[0]["ops"][0]["kind"] == "create"
    assert messages[0]["ops"][0]["object"] == ids.get_id(restored) != old_id


# -- Applying -----------------------------------------------------------------------------


def test_create_builds_the_object_it_describes(addon):
    collab_id = _new_id()

    _receive(_create_op(collab_id))

    obj = ids.find_object(collab_id)
    assert obj is not None
    assert obj.name == "Cube"
    assert obj.type == "MESH"
    assert tuple(obj.location) == pytest.approx((1.0, 2.0, 3.0))
    assert obj.rotation_mode == "XYZ"
    assert tuple(obj.rotation_euler) == pytest.approx((0.0, 0.0, 1.5))
    assert tuple(obj.scale) == pytest.approx((2.0, 2.0, 2.0))
    assert len(obj.data.vertices) == len(CUBE_VERTICES)
    assert [tuple(polygon.vertices) for polygon in obj.data.polygons] == CUBE_FACES
    assert obj.users_collection[0] == bpy.context.scene.collection


def test_create_links_into_the_named_collection(addon):
    collection = bpy.data.collections.new("Props")
    bpy.context.scene.collection.children.link(collection)
    collab_id = _new_id()

    _receive(_create_op(collab_id, collection="Props"))

    assert ids.find_object(collab_id).users_collection[0] == collection


@pytest.mark.parametrize("link_elsewhere", [False, True], ids=["no-such", "not-in-this-scene"])
def test_create_falls_back_to_the_scene_collection(addon, link_elsewhere):
    if link_elsewhere:
        bpy.data.collections.new("Props")  # exists, but isn't linked into the scene
    collab_id = _new_id()

    _receive(_create_op(collab_id, collection="Props"))

    assert ids.find_object(collab_id).users_collection[0] == bpy.context.scene.collection


def test_create_when_the_name_is_taken_still_applies(addon):
    _add_cube("Cube")
    collab_id = _new_id()

    _receive(_create_op(collab_id))

    assert ids.find_object(collab_id).name == "Cube.001"  # Blender's rename; that's fine


def test_create_twice_makes_one_object(addon):
    collab_id = _new_id()

    _receive(_create_op(collab_id, lamport=1))
    _receive(_create_op(collab_id, lamport=2, name="Other"))

    assert len(bpy.context.scene.objects) == 1
    assert ids.find_object(collab_id).name == "Cube"


def test_create_and_set_in_one_batch(addon):
    collab_id = _new_id()

    _receive(_create_op(collab_id, lamport=1), _location_op(collab_id, [7.0, 7.0, 7.0], lamport=2))

    assert tuple(ids.find_object(collab_id).location) == pytest.approx((7.0, 7.0, 7.0))


def test_malformed_create_leaves_nothing_behind(addon):
    good = _new_id()
    bad = _create_op()
    bad["transform"] = {"location": "nope"}

    _receive(bad, _create_op(good))  # must not raise

    assert list(bpy.context.scene.objects) == [ids.find_object(good)]
    assert len(bpy.data.objects) == 1
    assert len(bpy.data.meshes) == 1


def test_create_with_a_degenerate_face_does_not_crash(addon):
    collab_id = _new_id()

    _receive(_create_op(collab_id, mesh={"vertices": [[0, 0, 0], [1, 0, 0]], "faces": [[0, 0, 1]]}))

    assert len(ids.find_object(collab_id).data.polygons) == 0  # mesh.validate() dropped it


def test_create_and_delete_advance_the_lamport_clock(addon):
    collab_id = _new_id()

    _receive(_create_op(collab_id, lamport=500), _delete_op(collab_id, lamport=900))

    assert ordering.clock.tick() > 900


def test_delete_removes_the_object_and_its_mesh(addon):
    collab_id = _new_id()
    _receive(_create_op(collab_id))

    _receive(_delete_op(collab_id))

    assert ids.find_object(collab_id) is None
    assert collab_id in ordering.tombstones
    assert len(bpy.data.objects) == 0
    assert len(bpy.data.meshes) == 0


def test_delete_keeps_a_mesh_another_object_still_uses(addon):
    obj = _add_cube()
    other = bpy.data.objects.new("Linked", obj.data)
    bpy.context.scene.collection.objects.link(other)
    ids.ensure_ids()

    _receive(_delete_op(ids.get_id(obj)))

    assert other.data.name == "Cube"
    assert len(bpy.data.meshes) == 1


def test_delete_for_an_unknown_id_records_the_tombstone(addon):
    collab_id = _new_id()

    _receive(_delete_op(collab_id), _delete_op(collab_id, lamport=3))  # twice: still a no-op

    assert collab_id in ordering.tombstones


def test_delete_then_create_of_the_same_id_makes_nothing(addon):
    collab_id = _new_id()

    _receive(_delete_op(collab_id, lamport=1))
    _receive(_create_op(collab_id, lamport=2))

    assert ids.find_object(collab_id) is None
    assert len(bpy.data.objects) == 0


def test_delete_wins_over_a_later_set_whatever_its_timestamp(addon):
    collab_id = _new_id()
    _receive(_create_op(collab_id, lamport=1))
    _receive(_delete_op(collab_id, lamport=2))

    _receive(_location_op(collab_id, [9.0, 9.0, 9.0], lamport=1000))

    assert ids.find_object(collab_id) is None


def test_set_for_a_tombstoned_id_skips_an_object_still_in_the_scene(addon):
    # Undo can restore an object under a tombstoned ID before the next flush retires it.
    obj = _add_cube()
    ids.ensure_ids()
    ordering.tombstones.add(ids.get_id(obj))

    _receive(_location_op(ids.get_id(obj), [9.0, 9.0, 9.0], lamport=1000))

    assert tuple(obj.location) == pytest.approx((0.0, 0.0, 0.0))


def test_set_before_its_create_is_dropped_not_buffered(addon):
    # Protocol rule 9: the object ends up with the create's transform, not the set's.
    collab_id = _new_id()

    _receive(_location_op(collab_id, [9.0, 9.0, 9.0], lamport=2))
    assert ids.find_object(collab_id) is None

    _receive(_create_op(collab_id, lamport=1))
    assert tuple(ids.find_object(collab_id).location) == pytest.approx((1.0, 2.0, 3.0))


@pytest.mark.parametrize("order", list(itertools.permutations(("create", "set", "delete"))))
def test_a_delete_wins_in_every_delivery_order(addon, order):
    collab_id = _new_id()
    ops = {
        "create": _create_op(collab_id, lamport=1),
        "set": _location_op(collab_id, [9.0, 9.0, 9.0], lamport=3),
        "delete": _delete_op(collab_id, lamport=2),
    }

    for kind in order:
        _receive(ops[kind])

    assert ids.find_object(collab_id) is None
    assert collab_id in ordering.tombstones


def test_replaying_a_missed_create_and_delete_leaves_no_object(addon):
    # The client half of catch-up: #20 will feed a reconnecting client the log it missed,
    # as ordinary `ops`. The server half can't be tested until #19 / #20 exist.
    collab_id = _new_id()

    _receive(
        _create_op(collab_id, lamport=1),
        _location_op(collab_id, [1.0, 1.0, 1.0], lamport=2),
        _delete_op(collab_id, lamport=3),
    )
    _receive(_create_op(collab_id, lamport=1))  # the same log replayed after another drop

    assert ids.find_object(collab_id) is None
    assert len(bpy.data.objects) == 0


def test_applied_create_and_delete_are_not_echoed(sent):
    collab_id = _new_id()

    _receive(_create_op(collab_id))
    _settle()
    detect._mark_dirty()
    _settle_and_flush()
    _receive(_delete_op(collab_id))
    _settle()
    detect._mark_dirty()
    _settle_and_flush()

    assert sent == []


def test_b_moves_while_a_deletes_on_bs_side(sent):
    # B's pending move still goes out first; then A's delete removes it, without an echo.
    obj = _add_cube()
    _settle_and_flush()
    collab_id = ids.get_id(obj)
    sent.clear()

    obj.location = (5.0, 0.0, 0.0)
    _settle()
    _receive(_delete_op(collab_id, lamport=1000))
    detect._mark_dirty()
    _settle_and_flush()

    assert [[op["kind"] for op in message["ops"]] for message in sent] == [["set"]]
    assert ids.find_object(collab_id) is None


def test_b_moves_while_a_deletes_on_as_side(sent):
    # A has already deleted it, so B's move arriving afterwards changes nothing.
    obj = _add_cube()
    _settle_and_flush()
    collab_id = ids.get_id(obj)
    bpy.data.objects.remove(obj)
    _settle_and_flush()
    sent.clear()

    _receive(_location_op(collab_id, [5.0, 0.0, 0.0], lamport=1000))
    _settle()
    detect._mark_dirty()
    _settle_and_flush()

    assert ids.find_object(collab_id) is None
    assert sent == []


def test_round_trip_create_set_delete_into_an_empty_scene(sent, monkeypatch):
    # Client A: add a cube in a collection, move it, delete it. Keep what it sent.
    collection = bpy.data.collections.new("Props")
    bpy.context.scene.collection.children.link(collection)
    obj = _add_cube(collection=collection)
    obj.location = (1.0, 2.0, 3.0)
    obj.rotation_euler = (0.1, 0.2, 0.3)
    _settle_and_flush()
    collab_id = ids.get_id(obj)
    expected_rotation = tuple(obj.rotation_euler)
    obj.location = (4.0, 5.0, 6.0)
    _settle_and_flush()
    bpy.data.objects.remove(obj)
    _settle_and_flush()
    detect.stop()
    assert [[op["kind"] for op in message["ops"]] for message in sent] == [
        ["create"],
        ["set"],
        ["delete"],
    ]
    for message in sent:
        jsonschema.validate(instance=message, schema=SCHEMA)

    # Client B: an empty scene (with the same collection) and a new origin, receiving exactly
    # that as JSON. Both clients share one process, so B needs its own ordering state too.
    wire = [json.loads(json.dumps(message)) for message in sent]
    ordering.tombstones.clear()
    monkeypatch.setattr(ordering, "versions", ordering.Versions())
    bpy.data.meshes.remove(bpy.data.meshes["Cube"])
    echoes = []
    detect.start(echoes.append)

    apply.apply_message(wire[0])
    received = ids.find_object(collab_id)
    assert tuple(received.location) == pytest.approx((1.0, 2.0, 3.0))
    assert tuple(received.rotation_euler) == pytest.approx(expected_rotation)
    assert tuple(received.scale) == pytest.approx((1.0, 1.0, 1.0))
    assert received.users_collection[0] == collection
    assert len(received.data.vertices) == len(CUBE_VERTICES)
    assert len(received.data.polygons) == len(CUBE_FACES)

    apply.apply_message(wire[1])
    assert tuple(received.location) == pytest.approx((4.0, 5.0, 6.0))

    apply.apply_message(wire[2])
    assert ids.find_object(collab_id) is None
    assert collab_id in ordering.tombstones
    assert echoes == []
