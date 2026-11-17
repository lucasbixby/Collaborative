# Blender add-on

Targets **Blender 5.2 LTS** (bundled Python 3.13).

| File | Role |
|---|---|
| `__init__.py` | `bl_info`, register / unregister |
| `session.py` | The room this Blender was launched into: server, token, room, role, from the environment |
| `operators.py`, `panel.py` | Joining (by itself, at startup) and leaving; the sidebar status |
| `detect.py` | Detect local changes → operations |
| `apply.py` | Apply remote operations, guarded against echo loops |
| `ordering.py` | Lamport clock, last-writer-wins versions, tombstones |
| `ids.py` | Stable object IDs, shared by everyone who opens the room's file |
| `saving.py` | Host save → upload the file; guest save → ask the host |
| `client.py` | WebSocket on background threads, a queue to the main thread |
| `log.py` | `log(...)`: terminal output tagged with the client name (A / B) |
| `timing.py` | Latency timing, off unless `COLLAB_TIMING` is set (`docs/latency.md`) |

People never install this by hand: the Collaborative app starts Blender with
`desktop/blender/launch.py`, which loads the add-on for that session.

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
depends on.

`tests/test_convergence_vectors.py` feeds the shared scenarios in `tests/vectors/convergence.json`
(repo root, written by the server's convergence test) through the real `apply_message` and
checks the scene matches the reference model's. A scenario marked `known_divergence` is a
strict xfail: today that's two objects renamed to the same name (Blender adds `.001`).

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

**Testing sync by hand:** the normal way is the app (`desktop/`): two accounts, one hosts a
room, the other joins, both press Launch Blender. Without the app, give Blender the session
the app would, from `server/`:

```bash
python3 scripts/admin.py create-user alice && python3 scripts/admin.py create-user bob
python3 scripts/admin.py create-room demo --owner alice --room-password "open sesame"
python3 scripts/admin.py add-member demo bob --role editor
COLLAB_ROOM=demo COLLAB_ROLE=owner  COLLAB_USERNAME=alice COLLAB_TOKEN=$(python3 scripts/admin.py token alice) ../addon/scripts/blender.sh shared.blend &
COLLAB_ROOM=demo COLLAB_ROLE=editor COLLAB_USERNAME=bob   COLLAB_TOKEN=$(python3 scripts/admin.py token bob) COLLAB_CLIENT=B ../addon/scripts/blender.sh shared.blend
```

(`COLLAB_SERVER_URL` defaults to `ws://localhost:8000`.) Each Blender joins by itself.

- **Same file, same IDs.** On joining, every object without an ID gets one derived from the
  room and the object's name, so two Blenders that open the same file agree on which object is
  which. This happens once per file; an object added later gets a random ID.
- **Joining catches up.** The server first sends the room's current state as ordinary
  operations, and the panel shows "Catching up…" until it's in.
- **Merge on join.** Once caught up, a client offers the room every local mesh the room doesn't
  know yet, as a normal `create`. Cameras, lights and other non-meshes travel in the file, not
  as operations (`not synced yet` in the log).
- **Saving.** The host's save uploads the file. Anyone else's save writes their local copy and
  asks the host, and the panel shows how that went.
- **Viewers** apply what they receive and send nothing.
- **Refusals.** A 4401 / 4403 close stops the client (`docs/protocol.md`); the panel says why,
  and **Rejoin room** tries again.
- **Edits made while not in a room aren't sent.** If you move an object the room already knows
  while you're out of the room, the room's value replaces yours when you rejoin.

`server/scripts/ws_probe.py` can join the same room from a terminal to watch the traffic.

## VS Code tasks

Cmd+Shift+P › **Tasks: Run Task**: run tests, lint, set up, link into Blender, start one
or two Blender clients.

## Dependencies at runtime

Blender's Python can't `pip install` for end users, so the one runtime dependency,
`websocket-client`, is vendored in `collaborative_blender/vendor/`. The packages in
`requirements-dev.txt` are for development only and never ship.
