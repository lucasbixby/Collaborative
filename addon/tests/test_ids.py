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


# -- IDs shared by everyone who opens the same project file ------------------------------------


def _named(name):
    obj = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def test_shared_ids_depend_only_on_the_room_and_the_objects_name(scene):
    from collaborative_blender import ids

    cube, lamp = _named("Cube"), _named("Lamp")
    ids.assign_shared_ids("studio")
    first = (ids.get_id(cube), ids.get_id(lamp))

    # Another person's Blender, opening the same file: same names, so the same IDs.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    cube, lamp = _named("Cube"), _named("Lamp")
    ids.assign_shared_ids("studio")

    assert (ids.get_id(cube), ids.get_id(lamp)) == first
    assert first[0] != first[1]
    assert all(UUID_PATTERN.match(collab_id) for collab_id in first)


def test_shared_ids_differ_between_rooms(scene):
    from collaborative_blender import ids

    cube = _named("Cube")
    ids.assign_shared_ids("studio")
    in_studio = ids.get_id(cube)
    del cube[ids.COLLAB_ID], scene[ids.SHARED_IDS_DONE]
    ids.assign_shared_ids("garage")

    assert ids.get_id(cube) != in_studio


def test_an_object_that_already_has_an_id_keeps_it(scene):
    from collaborative_blender import ids

    cube = _named("Cube")
    kept = ids.assign_new_id(cube)
    ids.assign_shared_ids("studio")

    assert ids.get_id(cube) == kept


def test_an_object_added_after_the_first_time_is_new_not_whatever_had_its_name(scene):
    from collaborative_blender import ids

    old = _named("Cube")
    ids.assign_shared_ids("studio")
    old_id = ids.get_id(old)
    bpy.data.objects.remove(old)
    new = _named("Cube")  # same name as the object that was deleted

    ids.assign_shared_ids("studio")  # a later launch of the same file
    ids.ensure_ids()

    assert ids.get_id(new) not in (None, old_id)


def test_shared_ids_and_the_marker_are_saved_with_the_file(scene, tmp_path):
    from collaborative_blender import ids

    _named("Cube")
    ids.assign_shared_ids("studio")
    expected = ids.get_id(bpy.data.objects["Cube"])
    path = str(tmp_path / "shared.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)

    assert ids.get_id(bpy.data.objects["Cube"]) == expected
    assert bpy.context.scene.get(ids.SHARED_IDS_DONE)
