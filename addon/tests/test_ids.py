"""Tests for stable object IDs (#4)."""

import re

import bpy

from collaborative_blender import ids

UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _add_cube(name="Cube"):
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _duplicate(obj, *, linked):
    """Shift+D (linked=False) or Alt+D (linked=True), via the operator Blender itself runs."""
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    before = set(bpy.context.scene.objects)
    bpy.ops.object.duplicate(linked=linked)
    (copy,) = set(bpy.context.scene.objects) - before
    return copy


def test_ensure_ids_assigns_an_id_to_every_object(addon):
    a, b = _add_cube("A"), _add_cube("B")

    new = ids.ensure_ids()

    assert set(new) == {a, b}
    assert ids.get_id(a) is not None
    assert ids.get_id(b) is not None
    assert ids.get_id(a) != ids.get_id(b)


def test_ensure_ids_is_a_no_op_once_every_object_has_one(addon):
    _add_cube("A")
    _add_cube("B")
    ids.ensure_ids()
    before = {obj.name: ids.get_id(obj) for obj in bpy.context.scene.objects}

    assert ids.ensure_ids() == []
    assert {obj.name: ids.get_id(obj) for obj in bpy.context.scene.objects} == before


def test_shift_d_gives_the_copy_a_new_id(addon):
    original = _add_cube()
    ids.ensure_ids()
    original_id = ids.get_id(original)

    copy = _duplicate(original, linked=False)
    new = ids.ensure_ids()

    assert new == [copy]
    assert ids.get_id(original) == original_id
    assert ids.get_id(copy) != original_id


def test_alt_d_gives_the_linked_copy_a_new_id(addon):
    original = _add_cube()
    ids.ensure_ids()
    original_id = ids.get_id(original)

    copy = _duplicate(original, linked=True)
    new = ids.ensure_ids()

    assert new == [copy]
    assert ids.get_id(original) == original_id
    assert ids.get_id(copy) != original_id


def test_obj_copy_gives_the_copy_a_new_id(addon):
    original = _add_cube()
    ids.ensure_ids()
    original_id = ids.get_id(original)

    copy = original.copy()
    bpy.context.scene.collection.objects.link(copy)
    new = ids.ensure_ids()

    assert new == [copy]
    assert ids.get_id(original) == original_id
    assert ids.get_id(copy) != original_id


def test_rename_keeps_the_id(addon):
    obj = _add_cube()
    ids.ensure_ids()
    collab_id = ids.get_id(obj)

    obj.name = "Box"

    assert ids.get_id(obj) == collab_id
    assert ids.find_object(collab_id) == obj


def test_find_object_looks_up_by_id(addon):
    _add_cube("A")
    b = _add_cube("B")
    ids.ensure_ids()

    assert ids.find_object(ids.get_id(b)) == b
    assert ids.find_object("not-an-id") is None


def test_ids_match_the_protocol_uuid_pattern(addon):
    _add_cube("A")
    _add_cube("B")

    for obj in ids.ensure_ids():
        assert UUID_PATTERN.match(ids.get_id(obj))


def test_id_survives_save_and_reopen(addon, tmp_path):
    _add_cube()
    ids.ensure_ids()
    collab_id = ids.get_id(bpy.context.scene.objects["Cube"])

    path = tmp_path / "scene.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    bpy.ops.wm.open_mainfile(filepath=str(path))

    assert ids.get_id(bpy.context.scene.objects["Cube"]) == collab_id
