# Blender add-on

Targets **Blender 5.2 LTS** (bundled Python 3.13).

| File | Role |
|---|---|
| `__init__.py` | `bl_info`, register / unregister |
| `preferences.py` | Server URL and auth token |
| `panel.py`, `operators.py` | Sidebar UI: join / leave room, status |
| `detect.py` | Detect local changes → operations (the first spike) |
| `apply.py` | Apply remote operations, guarded against echo loops |
| `client.py` | WebSocket on a background thread, queue to the main thread |
| `log.py` | `log(...)`: terminal output tagged with the client name (A / B) |

## Development setup (once)

You need Blender 5.2 in `/Applications` (or set `BLENDER=/path/to/blender`) and either
[uv](https://docs.astral.sh/uv/) (`brew install uv`), Python 3.13, or conda.

```bash
addon/scripts/setup_dev.sh     # creates addon/.venv, installs test tools, runs the tests
addon/scripts/link_addon.sh    # makes your Blender load the add-on from this repo
```

`setup_dev.sh` installs **bpy**, the real Blender as a Python module (~900 MB), plus
type stubs so VS Code autocompletes `bpy`. In VS Code, accept the recommended
extensions when prompted (Python, Pylance, Ruff, Blender Development).

## Three ways to test

### 1. Automated, headless (fast; run constantly)

```bash
cd addon
.venv/bin/pytest
```

Or use the Testing panel (beaker icon) in VS Code. Tests run real Blender without a
window, enable the add-on through Blender's own add-on loader, and use a throwaway
preferences folder so your own Blender setup is untouched.

Fixtures in `tests/conftest.py`:

| Fixture | Gives you |
|---|---|
| `scene` | A fresh empty scene for each test |
| `addon` | The add-on enabled, and disabled again after the test |
| `depsgraph_log` | Records what `depsgraph_update_post` reports. Change something, then call `depsgraph_log.flush()` to get `(name, type, transform?, geometry?)` tuples |

Headless, nothing happens until the scene is evaluated, which `flush()` does. Operators
work (`bpy.ops.transform.translate(...)`, `bpy.ops.object.duplicate()`); interactive
mouse drags don't exist, so cover those by hand (below).

`tests/test_blender_assumptions.py` holds facts about Blender that change detection
depends on. Add to it as the spike finds more.

### 2. Interactive, one Blender (for UI and real mouse edits)

Either:

- **VS Code:** Cmd+Shift+P › **Blender: Start**. Blender opens with the add-on loaded and
  the debugger attached (breakpoints work), and saving a file reloads the add-on. Output
  appears in VS Code's terminal.
- **Terminal:** `addon/scripts/blender.sh`. Output appears in that terminal. After an edit,
  F3 › **Reload Scripts** in Blender.

Use `log(...)` from `log.py` rather than bare `print`, so lines are flushed immediately
and tagged with the client name.

### 3. Two Blenders (for sync)

```bash
addon/scripts/blender.sh --two
```

Starts clients **A** and **B** sharing one terminal; every `log(...)` line says which
client wrote it. Ctrl+C closes both.

## VS Code tasks

Cmd+Shift+P › **Tasks: Run Task**: run tests, lint, set up, link into Blender, start one
or two Blender clients.

## Dependencies at runtime

Blender's Python can't `pip install` cleanly for end users, so any WebSocket library
has to be vendored into this folder (or the stdlib used). Decide during the spike.
The packages in `requirements-dev.txt` are for development only and never ship.
