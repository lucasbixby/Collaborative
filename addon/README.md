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

**Testing sync by hand, until #20 (snapshots) exists:** two separately-opened Blenders
give the same objects different random `collab_id`s, so an operation from A would never
match an object in B. Both clients must open **the same saved `.blend` file**, so the IDs
`ensure_ids()` already assigned are identical on both sides (IDs are custom properties,
so they're saved in the file and survive reopening it, #4). To prepare one:

1. Open Blender once, add the objects you want to test with, join a room (the
   Collaborative panel) so detection runs and `ensure_ids()` tags everything, then leave.
2. Save the file (e.g. `shared.blend`).
3. Open that same file in both client A and client B.

With both on the same file and the server running (`uvicorn app.main:app`, see
`server/README.md`), **Join room** in both A and B with the same Room ID: edits in one
now reach the other through the relay (#11 / #12 / #13). `server/scripts/ws_probe.py` can
join the same room from a terminal to watch the traffic.

**Apply from clipboard** (Collaborative panel) is still there as a dev aid: paste a
logged batch (or a hand-written one) and apply it without a server, e.g. to check
last-writer-wins (#8 / #9) by hand.

## VS Code tasks

Cmd+Shift+P › **Tasks: Run Task**: run tests, lint, set up, link into Blender, start one
or two Blender clients.

## Dependencies at runtime

Blender's Python can't `pip install` cleanly for end users, so any WebSocket library
has to be vendored into this folder (or the stdlib used). Decide during the spike.
The packages in `requirements-dev.txt` are for development only and never ship.
