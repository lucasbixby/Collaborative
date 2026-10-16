# Blender add-on

Targets Blender 4.2+ (bundled Python 3.11).

| File | Role |
|---|---|
| `__init__.py` | `bl_info`, register / unregister |
| `preferences.py` | Server URL and auth token |
| `panel.py`, `operators.py` | Sidebar UI: join / leave room, status |
| `detect.py` | Detect local changes → operations (the first spike) |
| `apply.py` | Apply remote operations, guarded against echo loops |
| `client.py` | WebSocket on a background thread, queue to the main thread |

## Install for development

```bash
cd addon
zip -r collaborative_blender.zip collaborative_blender
```

Then in Blender: **Edit › Preferences › Add-ons › Install from Disk** and pick the zip.
For faster iteration, symlink `collaborative_blender` into Blender's add-ons folder instead
and use **Reload Scripts** after edits.

## Dependencies

Blender's Python can't `pip install` cleanly for end users, so any WebSocket library
has to be vendored into this folder (or the stdlib used). Decide during the spike.
