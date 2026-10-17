"""Blender behaviour that change detection relies on.

These test Blender, not our code. If a Blender upgrade changes any of them, this file
fails first and points at the assumption that broke. Extend it with whatever the
change-detection spike turns up (see docs/spike-notes.md once it exists).
"""

import bpy


def _add_cube(name="Cube"):
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    bpy.context.scene.collection.objects.link(obj)
    return obj


def test_moving_an_object_reports_a_transform_update(depsgraph_log):
    cube = _add_cube()
    depsgraph_log.flush()

    cube.location = (1.0, 2.0, 3.0)

    assert ("Cube", "Object", True, False) in depsgraph_log.flush()


def test_custom_property_change_reports_nothing(depsgraph_log):
    # Lets us tag objects with an ID (obj["collab_id"]) without generating updates.
    cube = _add_cube()
    depsgraph_log.flush()

    cube["collab_id"] = "abc"

    assert depsgraph_log.flush() == []


def test_renaming_reports_the_object_with_no_flags(depsgraph_log):
    # A rename can't be told apart from other flag-less updates, so objects need stable IDs.
    cube = _add_cube()
    depsgraph_log.flush()

    cube.name = "Box"

    assert ("Box", "Object", False, False) in depsgraph_log.flush()


def test_adding_an_object_reports_its_collection(depsgraph_log):
    # The collection update is the signal to compare the object set with the cache.
    depsgraph_log.flush()

    _add_cube()

    updates = depsgraph_log.flush()
    assert any(kind == "Collection" for _, kind, *_ in updates)
    assert any(name == "Cube" and kind == "Object" for name, kind, *_ in updates)


def test_deleting_an_object_does_not_report_the_object(depsgraph_log):
    # Deletions must be found by diffing the set of objects, not from depsgraph.updates.
    cube = _add_cube()
    depsgraph_log.flush()

    bpy.data.objects.remove(cube)

    names = {name for name, *_ in depsgraph_log.flush()}
    assert "Cube" not in names
