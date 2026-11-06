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
| `timing.py` | Latency timing, off unless `COLLAB_TIMING` is set (#24, `docs/latency.md`) |

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

**Testing sync by hand:** start the server (`uvicorn app.main:app`, or `docker compose up`;
see `server/README.md`), then **Join room** in both A and B with the same Room ID. The two
Blenders don't need the same file (#20):

- **Joining catches up.** The server first sends the room's current state as ordinary
  operations, and the panel shows "Catching up…" until it's in. A Blender with an empty scene
  ends up with every object in the room, and one that was away gets what it missed, deletes
  included.
- **Merge on join.** Once caught up, a client offers the room every local mesh the room doesn't
  know yet, as a normal `create`. So two Blenders joining with the default scene end up with
  both cubes (the second one arrives as `Cube.001`). Cameras, lights and other non-meshes stay
  local (`not synced yet`).
- **Only on Join.** A reconnect after a network drop doesn't offer anything again: edits made
  meanwhile are already queued and go out normally.
- **Edits made while not in a room aren't sent.** If you move an object the room already knows
  while you're out of the room, then rejoin, that move stays on your screen only, until someone
  edits the object again.

Opening the same saved `.blend` in both still works: objects whose IDs the room already knows
aren't offered again. `server/scripts/ws_probe.py` can join the same room from a terminal to
watch the traffic.

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
