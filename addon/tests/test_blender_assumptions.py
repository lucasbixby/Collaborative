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


def test_deleting_an_object_does_not_report_the_object(depsgraph_log):
    # Deletions must be found by diffing the set of objects, not from depsgraph.updates.
    cube = _add_cube()
    depsgraph_log.flush()

    bpy.data.objects.remove(cube)

    names = {name for name, *_ in depsgraph_log.flush()}
    assert "Cube" not in names
