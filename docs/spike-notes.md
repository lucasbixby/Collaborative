# Spike: Blender change detection (#3)

**Question:** can the add-on see every edit we need to sync through
`bpy.app.handlers.depsgraph_update_post` (Plan A), or does it need to poll scene state (Plan B)?

**Answer:** Plan A works, as long as the handler is used as a *trigger* and the actual changes
are found by comparing against a cache. No polling needed. Decisions D-018 to D-021 in
[devlog.md](devlog.md).

**Setup:** Blender 5.2 LTS on macOS, logging handler in `addon/collaborative_blender/detect.py`
printing each `depsgraph.updates` entry (data-block type, name, transform / geometry flags).
Tested by hand on 2026-10-16.

## Results

| Action | What the handler reported | Consequence for `detect.py` |
|---|---|---|
| Drag with G | ~50–60 updates per second, `transform` only, only the moved object | Too many to send one by one: mark objects dirty, send their current values every ~50 ms |
| Type a value in the N panel | An update, same as a drag | Non-operator edits are covered too |
| Rotate | Transform update | Rotation is covered; `rotation_mode` still has to be synced so the other client reads the right property |
| Add an object (Shift+A) | The new Object and its Mesh (transform + geometry), the Scene Collection and the target Collection, plus updates for other objects in the scene (camera, light, ...) | Being reported doesn't mean changed: diff values against the cache. Detect creation by comparing the object set. The create operation must carry the mesh data and the collection, since nothing says "cylinder" |
| Delete an object | Updates for the remaining objects and collections; the deleted object never appears | Detect deletion by comparing the object set with the cache |
| Rename (F2) | One update with the new name, no flags | Track objects by a stable ID (#4), not by name; a rename is a change to the `name` property |
| Duplicate (Shift+D) | Same pattern as adding an object | Handled by the object-set diff, as a create |
| Undo (Cmd+Z) | A scene-level update, no per-object detail | Run a full diff of all objects after undo / redo (`bpy.app.handlers.undo_post`, `redo_post`); object references are invalid after undo, so the cache must hold names / IDs, never objects |
| Move a vertex in Edit Mode | Mesh and Object updates with `geometry` | Mesh edits are detectable (stretch goal #26). Edit Mode keeps its own copy of the mesh, so reading vertex data needs care |

## Confirmed in automated tests

`addon/tests/test_blender_assumptions.py` (headless Blender 5.2): moving reports a transform
update; setting a custom property reports nothing; deleting doesn't report the object;
renaming reports the object with no flags; adding an object reports its collection.

## Still open

- **Adjust Last Operation:** after adding an object, change its settings in the bottom-left
  panel (e.g. Vertices 32 → 8). Does it look like a geometry change on the same object, or a
  delete and re-create with the same name?

## Resolved

- **Duplicates and IDs (#4):** Shift+D, Alt+D and `obj.copy()` all copy `obj["collab_id"]`, so
  a duplicate briefly shares its ID with the original. `ensure_ids()` in
  `addon/collaborative_blender/ids.py` resolves this by `session_uid`: the lowest keeps the
  shared ID, the rest are re-tagged. See D-031/D-032 in devlog.md.
- **Quaternion rotation (#5):** confirmed by hand in Blender 5.2 (10/20) — switching Rotation
  Mode to Quaternion via the dropdown and rotating produces a correct `set rotation` op
  (`"mode": "QUATERNION"`), matching `test_rotation_set_as_quaternion`.
- **Undo / redo and IDs (moved here from #4, closed by #5):** confirmed by hand in Blender
  5.2 (10/20) — an object keeps its `collab_id` across undo and redo, and a Shift+D copy
  still gets a new ID (keeping the original's) after undo and redo too.
