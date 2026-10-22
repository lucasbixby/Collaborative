# Development log

A running record of what was decided and built at each step of Collaborative, and why.
Newest entries go at the bottom of **Log**. Feature status lives on the GitHub Project board
(issues and milestones); this file explains the reasoning behind the work.

**Adding an entry** — one per working step (a feature, a spike, a change of plan):

```markdown
### YYYY-MM-DD · Short title (#issue)

What was done, in a sentence or two.

| Decision | Why |
|---|---|
| D-NNN: the choice made | The reason, and what was rejected |

**Details:** files, commands, anything someone continuing the work needs.
**Open / follow-up:** what is left, with issue numbers.
```

Decisions get a number (D-001, D-002, ...) so later entries can refer to them. When a decision
is reversed, add a new decision that says so and mark the old one in the index; don't edit history.

## Current status

| | |
|---|---|
| Phase | Prototype (due 10/24) |
| In progress | #11 WebSocket relay (implementation done; manual check open), #6 Apply remote operations (implementation done; manual check open), #8 Lamport clock, #9 last-writer-wins |
| Next up | #12 WebSocket client (connects #5/#6 to the relay) |
| Done | #1 Repository scaffold, #2 Add-on testing workflow, #3 Change-detection spike, #4 Stable object IDs, #5 Detect local transform changes, #7 Operation format |
| Loose ends | #11's manual check (two probes, one in another room); #6's manual check (two Blenders, same `.blend`); Adjust Last Operation spike item |

## Decision index

| ID | Decision | Date | Status |
|---|---|---|---|
| D-001 | Scope is Blender only | 10/12 | Active |
| D-002 | Sync model: apps run locally, server relays operations | 10/12 | Active |
| D-003 | FastAPI for the whole backend, not Cloudflare | 10/12 | Active |
| D-004 | SQLite in development, Postgres only if time allows | 10/12 | Active |
| D-005 | Asset storage behind an interface, local disk first | 10/12 | Active |
| D-006 | Lamport timestamps + last-writer-wins first | 10/12 | Active |
| D-007 | Sync engine is hand-written; AI for scaffolding and UI | 10/12 | Replaced by D-028 |
| D-008 | One repository with server/, addon/, web/, docs/ | 10/15 | Active |
| D-009 | Sync engine scaffolded as documented empty stubs | 10/15 | Replaced by D-028 |
| D-010 | Target Blender 5.2 LTS and Python 3.13 | 10/15 | Active |
| D-011 | Headless add-on tests with the `bpy` module from PyPI | 10/15 | Active |
| D-012 | Tests enable the add-on through Blender's own loader | 10/15 | Active |
| D-013 | Type stubs installed next to the real `bpy` | 10/15 | Active |
| D-014 | Develop against a symlinked add-on, not an installed copy | 10/15 | Active |
| D-015 | Log lines tagged with the client name (A / B) | 10/15 | Active |
| D-016 | Relax four type-checker rules for the add-on only | 10/15 | Active |
| D-017 | Track features as GitHub issues on a Project board | 10/15 | Active |
| D-018 | Plan A: depsgraph handler as the trigger, diff against a cache | 10/16 | Active |
| D-019 | Coalesce changes and send every ~50 ms | 10/16 | Active |
| D-020 | Creates, deletes and undo found by a full object-set diff | 10/16 | Active |
| D-021 | Create operations carry mesh data and the target collection | 10/16 | Active |
| D-022 | One `set` operation per property: location, rotation, scale, name | 10/19 | Active |
| D-023 | Rotation sent as mode + values in one property | 10/19 | Active |
| D-024 | Operations travel in versioned batches (`{"v": 1, "type": "ops", "ops": [...]}`) | 10/19 | Active |
| D-025 | Every operation carries its own Lamport timestamp and origin | 10/19 | Active |
| D-026 | Deletes win over later sets; creates are idempotent | 10/19 | Active |
| D-027 | Claude may write sync-engine tests from the spec; the implementation stays hand-written | 10/19 | Replaced by D-028 |
| D-028 | Claude writes all code, with a 2–3 sentence explanation of each piece | 10/20 | Active |
| D-029 | Operations parsed with strict Pydantic models; `parse_message` is the single entry point | 10/20 | Active |
| D-030 | Planning chat manages the project; Claude Code on my Mac implements | 10/20 | Active |
| D-031 | Object IDs live in the custom property `obj["collab_id"]`, a lowercase uuid4 string | 10/20 | Active |
| D-032 | Duplicate IDs are resolved by `session_uid`: the lowest keeps the ID, the rest get new ones | 10/20 | Active |
| D-033 | Detection handlers only set a dirty flag; a 50 ms timer diffs the whole scene against a cache keyed by `collab_id` | 10/20 | Active |
| D-034 | A new object enters the cache silently (no op for its initial state); a deleted object silently leaves it | 10/20 | Active |
| D-035 | `suppressed()` refreshes the cache from the scene on exit, without emitting | 10/20 | Active |
| D-036 | Start / Stop detection button in the panel logs batches as JSON until Join room (#13) exists | 10/20 | Active |
| D-037 | `jsonschema` added as a dev dependency so a contract test validates emitted messages against protocol.md's schema directly | 10/20 | Active |
| D-038 | `suppressed()` flushes pending local edits before its outermost block runs | 10/20 | Active |
| D-039 | Rooms are implicit and in-memory: created on first join, removed on last leave | 10/20 | Active |
| D-040 | An invalid message gets an `error` reply to the sender only; the connection stays open | 10/20 | Active |
| D-041 | Server tests share one `TestClient` portal (`with TestClient(...)`) instead of one per websocket connection | 10/20 | Active |
| D-042 | `ruff` pinned to 0.17.1 in both `server/pyproject.toml` and `addon/requirements-dev.txt` | 10/20 | Active |
| D-043 | `create_app()` configures logging for the `app` logger namespace at startup | 10/20 | Active |
| D-044 | `apply_message` runs its whole batch inside one `detect.suppressed()` block, with objects looked up once per batch | 10/21 | Active |
| D-045 | Until #20, both clients must open the same saved `.blend` so `collab_id`s already match | 10/21 | Active |

## Log

### 2026-10-12 · Project proposal

Wrote the proposal (`docs/proposal.pdf`) for CS 407/507: real-time collaborative editing for
creative apps, starting with Blender. Prototype due 10/24, feature freeze 11/16, demo 11/23.

| Decision | Why |
|---|---|
| D-001: Blender only; other apps are future adapters | Blender has an open Python API. Adobe's extension systems are limited and bound by their terms of service. A narrow scope fits six weeks. |
| D-002: Sync model — each user runs Blender with an add-on; the server only relays small operations | No hosting or streaming of licensed apps (every user keeps their own legal copy), and small operations keep latency low. |
| D-003: FastAPI for real-time sync, REST, storage and auth | One server I control holds all sync state, which is easier to build, test and reason about than splitting it across Cloudflare Workers / Durable Objects. |
| D-004: SQLite first, Postgres if time allows | Zero setup during development; switching later is a database URL change. |
| D-005: Large assets stored by content hash behind a storage interface | Object storage (e.g. Cloudflare R2) can be added later without touching the sync engine. |
| D-006: Lamport timestamps and last-writer-wins per property | Simplest ordering that guarantees convergence. CRDT-style merging is a stretch goal (#29). |
| D-007: Hand-write and fully understand the sync engine; use Claude Code for scaffolding and UI | The sync engine is the core of the project and what it is graded on, so it must be my own work and covered by tests. |

**Open / follow-up:** biggest risk is Blender change detection, so it is spiked first (#3).

### 2026-10-15 · Repository scaffold (#1)

Created the folder structure for all parts of the system, with a runnable FastAPI server
(health check), a Blender add-on that loads and shows a sidebar panel, a React + TypeScript
app, Docker setup and CI. Commits 931dcd1, c364af7.

| Decision | Why |
|---|---|
| D-008: One repository: `server/`, `addon/`, `web/`, `docs/` | The add-on and server must agree on one protocol (`docs/protocol.md`); one repo keeps them changing together, with one CI and one history. |
| D-009: `server/app/sync/` files contain only a description of their job, no code | Keeps D-007: the structure is ready, the implementation is mine. `server/app/sync/README.md` lists each file's responsibility. |

**Details:**
- Server modules: `api/` (REST), `realtime/` (WebSocket relay), `sync/` (engine), `auth/`, `db/`, `storage/`.
- Add-on modules: `detect.py`, `apply.py`, `client.py` stubs; `preferences.py`, `panel.py`, `operators.py` working.
- The proposal moved to `docs/proposal.pdf`; `docs/architecture.md` maps the proposal to folders.
- `.gitignore` and the CI workflow were missing from the first push (Finder hides files starting
  with a dot when copying) and were added in c364af7.

**Open / follow-up:** `docker compose up` has not been tested yet (#23).

### 2026-10-15 · Add-on testing workflow (#2)

Set up three ways to test the add-on before writing any feature code: automated headless tests,
one interactive Blender, and two Blenders side by side. Commit 0a43a84. How-to in `addon/README.md`.

| Decision | Why |
|---|---|
| D-010: Blender 5.2 LTS, Python 3.13; `bl_info` minimum raised from 4.2 to 5.2 | 5.2.2 is the newest LTS release and the newest `bpy` on PyPI. Tests run against exactly one version, so the add-on claims only that one. |
| D-011: Automated tests run real Blender through the `bpy` package from PyPI | Plain `pytest` can drive real Blender without a window: fast (under a second), works in VS Code's Testing panel and in CI. Rejected: running scripts with `blender --background`, which is harder to wire into pytest. |
| D-012: Tests load the add-on with `addon_utils.enable` from a temporary scripts folder | Same code path a real Blender uses (catches `bl_info` and registration mistakes), and never touches my real Blender preferences. |
| D-013: `fake-bpy-module-5.2` installed in the same environment as `bpy` | Gives VS Code autocomplete and type checks for `bpy`. It installs as `bpy-stubs`, so it doesn't replace the real module. |
| D-014: Blender loads the add-on through a symlink to the repo (`link_addon.sh`) | Edits apply after Reload Scripts, with no zip / reinstall cycle. The VS Code Blender Development extension adds reload-on-save and breakpoints. |
| D-015: `log()` prefixes output with `COLLAB_CLIENT` (A / B) and flushes immediately | `blender.sh --two` runs two clients in one terminal; tagged lines show which client did what. |
| D-016: Four type-checker rules off for `addon/` only (`pyrightconfig.json`) | Blender's property syntax, operator return values and possibly-`None` UI objects are flagged in all Blender code. Everything else stays checked. |

**Details:**
- Fixtures in `addon/tests/conftest.py`: `scene`, `addon`, `depsgraph_log`.
- Scripts in `addon/scripts/`: `setup_dev.sh`, `link_addon.sh`, `blender.sh` (`--two`).
- CI runs add-on lint and tests on Ubuntu (needs a few X11/OpenGL libraries).
- Confirmed headless with Blender 5.2 (now tests in `test_blender_assumptions.py`): moving an
  object reports a transform update; setting a custom property reports nothing; deleting an object
  does not report the object itself (only the scene and collection).
- Not verified by Claude: the real Blender app on macOS (download blocked in its workspace),
  and the conda path in `setup_dev.sh`. Setup and linking were then run successfully on my Mac.

### 2026-10-15 · Project tracking (#1–#29)

Set up tracking for the rest of the project: 29 issues covering every must-have and stretch
feature from the proposal, grouped by milestones and labels, plus this log.

| Decision | Why |
|---|---|
| D-017: One GitHub issue per feature, on a Project board with Todo / In Progress / Done | Commits can close issues (`Closes #12`), which moves the card to Done. Milestones mirror the proposal's dates. Claude's GitHub access can create issues but not Project boards, so the board itself is created by hand in GitHub. |

**Details:**
- Milestones: Prototype (10/24), Feature freeze (11/16), Demo (11/23). Stretch goals have the
  `stretch` label and no milestone.
- Labels: `area: add-on`, `area: server`, `area: sync engine`, `area: web`, `area: infra`,
  `spike`, `testing`, `stretch`, and `hand-written` for work I write myself (D-007).

**Open / follow-up:** next is the change-detection spike (#3).

### 2026-10-16 · Change-detection spike (#3)

Wrote a logging handler in `detect.py` and recorded what Blender 5.2 reports for each kind of
edit (drag, N panel, rotate, add, delete, rename, duplicate, undo, Edit Mode). Plan A works;
polling isn't needed. Full results in [spike-notes.md](spike-notes.md).

| Decision | Why |
|---|---|
| D-018: `depsgraph_update_post` decides *when* to look; comparing against a cache of last-known values decides *what* changed | The handler fires for every edit we tried, including N-panel typing, but it only says which data-blocks were touched, not their values, and it also reports objects that didn't change (adding one object reports the camera and light too). Rejected: polling every object on a timer (Plan B), which costs work even when nothing changes. |
| D-019: The handler only marks objects dirty; a ~50 ms timer sends their current values | Dragging fires 50–60 updates per second per object. Sending the latest value 20 times a second still looks smooth and stays well inside the 200 ms latency target. The final position is always sent. |
| D-020: Creations, deletions and undo / redo are found by comparing the scene's object set with the cache | A deleted object never appears in the updates, and undo only reports the scene. A full diff on collection updates and on `undo_post` / `redo_post` catches all three with one mechanism. |
| D-021: A create operation includes the mesh data (vertices, faces), transform and collection | The updates don't say what kind of object was added, so the other client can't rebuild it from anything less. Large meshes go to content-addressed storage later (#27). |

**Details:**
- Renames report one flag-less update, so objects are tracked by a stable ID (`obj["collab_id"]`, #4), never by name; the cache stores IDs and values, never object references (undo invalidates them).
- Edit Mode vertex moves do report `geometry` on the Object and Mesh, so mesh sync (#26) is feasible.
- Two new assumption tests: rename reports a flag-less update; adding an object reports its collection.

**Open / follow-up:** Adjust Last Operation behaviour, Shift+D copying `collab_id`, quaternion
rotation (listed in spike-notes.md). Next: #4 stable IDs and #5 transform detection.

### 2026-10-19 · Operation format spec (#7)

Wrote the wire format for operations into [protocol.md](protocol.md): conventions, the `ops`
batch message, `set` / `create` / `delete` operations, ordering and validation rules, a JSON
Schema, and example messages. Based on the spike's findings. Claude drafted the spec from the
spike results at my request; decisions are marked **Proposed** until I've reviewed them.
`operations.py` and its tests stay hand-written (D-007).

| Decision | Why |
|---|---|
| D-022: One `set` per property (`location`, `rotation`, `scale`, `name`) | Last-writer-wins works per (object, property), so if one user moves an object while another rotates it, both changes survive. Rejected: one operation for the whole transform (one edit would overwrite the other); per-component (`location.x`), which adds overhead for no real benefit. |
| D-023: `rotation` is `{"mode", "values"}`: 3 radians for Euler modes, 4 numbers for quaternion / axis-angle | Blender stores each rotation mode in a different property. Sending mode and values together means they can never be out of sync on the receiver. |
| D-024: Operations travel in batches inside a versioned envelope | The 50 ms send timer (D-019) produces several operations at once; one message per batch saves overhead. A version number from day one makes later format changes detectable. |
| D-025: Every operation carries its own `lamport` and `origin` | The server logs, orders and relays operations individually, so each must stand alone. (`lamport`, `origin`) is also unique, so it serves as the operation's ID without a separate field. |
| D-026: Deletes win (receivers keep tombstones of deleted IDs); duplicate creates are ignored | If one user deletes an object while another is still dragging it, late moves must not bring it back. Ignoring repeated creates makes resending safe. |

**Details:**
- Checked: the JSON Schema is valid 2020-12; all example messages pass it; 15 kinds of bad
  message are rejected (wrong vector size, unknown property, extra field, bad rotation mode,
  Lamport 0, name instead of UUID, ...). Property names, rotation modes and value sizes were
  checked against Blender 5.2.
- Rules the schema can't express (face indices in range, 64 KiB size, `origin` matching the
  connection, name byte length, rejecting NaN) are listed in protocol.md for validation (#10).
- The example messages in protocol.md parse as JSON, so tests on both sides can load them.

**Open / follow-up:** D-022 to D-026 reviewed and accepted (10/19). Next: write `operations.py` and
`server/tests/sync/` tests (hand-written). `join`, `catch_up`, `snapshot` and `error` messages
are TODO with #11, #20 and #10.

**Future work:** discussed locking objects so only one person edits them at a time (pessimistic
concurrency). Selection-based locks were rejected: people select constantly, and Select All
would lock the whole scene. The design that fits is a hard lock while someone is in Edit Mode on
a mesh, where conflicting edits can't be merged, plus soft "selected by" indicators. The server
acts as lock manager with try-lock (no waiting, so no deadlock), releasing on exit, disconnect
or lease timeout. Recorded as stretch issue #30, to ship with mesh sync (#26).

### 2026-10-19 · Tests for the operation format (#7)

Claude wrote `server/tests/sync/test_operations.py` from `docs/protocol.md`, at my request, on
branch `issue-7-operations`. I write `server/app/sync/operations.py` to make them pass, then
merge with `Closes #7`.

| Decision | Why |
|---|---|
| D-027: Claude may write tests for the sync engine from the spec; the implementation stays hand-written (amends D-007) | The tests restate `protocol.md` as checks, so they hold no design of their own; the design is in the spec I approved. Writing the code that passes them is where the understanding comes from, and that stays mine. |
| Tests go on a branch until `operations.py` passes them | They fail until the implementation exists; keeping them off `main` keeps CI green. |

**Details:**
- The tests define the interface: `parse_message(raw)` raises `ValueError` for anything the
  spec rejects (including messages over 64 KiB); `serialize_message(message)` returns JSON text.
- 68 tests: every example message in protocol.md parses (they are read from the file itself);
  round trip; 36 rejections (wrong sizes, unknown fields, Lamport `0` / `1.5` / `true`, bad
  UUIDs, NaN, Infinity, name byte length, face indices, oversize); 13 valid variations.
- Checked against throwaway implementations that were never committed: a correct one passes
  all 68; one with Pydantic's default settings fails 8 (strings as numbers, `true` as an int,
  UUID formats, NaN / Infinity), which are the traps the tests exist to catch.

**Open / follow-up:** write `operations.py` on the branch, run `pytest tests/sync`, merge.

### 2026-10-20 · Claude writes all code; operation format implemented (#7)

Changed how the project is built: Claude now writes all the code, including the sync engine,
and explains each piece in 2–3 sentences (what it does and why). Then implemented
`server/app/sync/operations.py`, which passes all 68 tests from the previous entry. Closes #7.

| Decision | Why |
|---|---|
| D-028: Claude writes all code, including the sync engine, with a short explanation of each piece; replaces D-007, D-009 and D-027 | My choice, to keep the project moving toward the prototype (10/24) and demo (11/23). The explanations keep me able to explain and defend every part of the code. The course proposal said the sync engine would be hand-written, so this change is recorded here with its date. |
| D-029: `operations.py` parses messages with strict Pydantic models (`extra="forbid"`, `strict=True`, `allow_inf_nan=False`), chosen by discriminated unions on `kind`, then `property` / `mode` | One model per schema section mirrors `protocol.md` directly. Strict mode is what makes the code reject what the spec rejects; Pydantic's defaults accept `"1.5"` as a number, `true` as an integer, and NaN. `parse_message` checks the 64 KiB limit before parsing and never uses `json.loads`, which accepts NaN. |

**Details:**
- The `hand-written` label was removed from the issues and deleted; `CLAUDE.md`, the sync
  READMEs, `architecture.md` and `protocol.md` were updated to match.
- IDs are plain strings matching the UUID pattern rather than Pydantic's `UUID` type, so each ID
  has exactly one spelling when compared.
- Rules the JSON Schema can't express live in validators: face indices in range, names within
  255 bytes of UTF-8.
- Each operation exposes `op_id` = (`lamport`, `origin`), the ordering key for #8 and #9.
- Rejections carry readable reasons (e.g. `ops.0.set.location.lamport: Input should be a valid
  integer`), useful later for the `error` message (#10).

**Open / follow-up:** #4 stable object IDs and #5 transform detection on the add-on side; #8
Lamport clock and #9 last-writer-wins on the server side.

### 2026-10-20 · New way of working; #4 designed

| Decision | Why |
|---|---|
| D-030: The claude.ai chat is the project manager (issues, board, specs, reviews, devlog for planning); Claude Code running in my local repo is the worker that implements | Claude Code works on my files directly and runs commands on my Mac, without the sync and permission problems of editing through the chat. The chat keeps the overview across sessions. `CLAUDE.md` tells the worker to read the issue first, pull before starting, and update the devlog itself. |

Issue #4 now holds the full design (custom property `collab_id`, duplicates resolved by
lowest `session_uid`) and findings verified in headless Blender 5.2: every copy method
(Shift+D, Alt+D, `obj.copy()`) copies the ID, renames keep it, and it survives save and
reopen while `session_uid` doesn't. This answers the duplicate-ID question left open in
spike-notes.md.

### 2026-10-20 · Stable object IDs (#4)

Added `addon/collaborative_blender/ids.py`: `get_id`, `find_object` and `ensure_ids`, which
assigns `obj["collab_id"]` to every object in the scene and resolves duplicates. Also fixed
the loose end from the change-detection spike (`unregister()` now calls `detect.stop()`).
Closes #4.

| Decision | Why |
|---|---|
| D-031: Object IDs live in `obj["collab_id"]`, a lowercase uuid4 string matching the UUID pattern in protocol.md | A custom property copies with the object (Shift+D, Alt+D, `obj.copy()`), survives renames and save/reopen, and setting it fires no depsgraph update — unlike `session_uid`, which is reassigned on every file open and can't be sent over the wire. One spelling (lowercase) keeps IDs comparable as plain strings, matching `operations.py`'s `Uuid` type. |
| D-032: Duplicate IDs are resolved by `session_uid`: the lowest keeps the shared ID, every other holder gets a new one | Any copy method leaves two objects sharing one ID until `ensure_ids` next runs. Blender always gives a copy a higher `session_uid` than its source (verified for Shift+D, Alt+D and `obj.copy()`), so sorting by it picks the original without tracking copy history. Behaviour across undo is not verified yet; that check moved to #5. |

**Details:**
- `ensure_ids()` groups scene objects by `collab_id` first (unassigned objects go straight to
  the "needs an ID" list), then re-tags every object past the first in each group that shares
  one. It returns exactly the objects that were (re)tagged, so callers can tell what changed.
- `get_id(obj)` and `find_object(collab_id)` are the read side: a plain property read and a
  linear scan of `bpy.context.scene.objects` respectively — the scene is small enough that an
  index isn't worth the bookkeeping yet.
- Tests in `addon/tests/test_ids.py` cover: assigning IDs to a bare scene, a second call being
  a no-op, Shift+D / Alt+D / `obj.copy()` giving the copy (not the original) a new ID, rename
  keeping the ID, save + reopen keeping the ID, and every generated ID matching protocol.md's
  UUID pattern. Confirms the findings recorded in the issue rather than re-deriving them.
- `detect.stop()` wasn't wired into `unregister()`; harmless today since nothing calls
  `detect.start()` yet (that lands with #5), but left unregistering an idempotent handler
  removal would have been a live bug once it did.

**Open / follow-up:** #5 uses `ids.ensure_ids()` / `ids.get_id()` to track objects by ID
instead of by name when turning depsgraph updates into operations.

### 2026-10-20 · Detect local transform changes (#5)

Rewrote `addon/collaborative_blender/detect.py` per the design in the issue: handlers that
only set a dirty flag, and a 50 ms timer that diffs the whole scene against a cache and
turns changed properties into `set` operations. Added a Start / Stop detection dev-aid
button to the panel. Refs #5 — the issue stays open until the manual checks below are done.

| Decision | Why |
|---|---|
| D-033: `depsgraph_update_post` / `undo_post` / `redo_post` only set a dirty flag; `flush()` (plain function, run by a `bpy.app.timers` tick every 50 ms) does `ids.ensure_ids()` then diffs every object against a cache keyed by `collab_id` | One mechanism covers drags, N-panel edits, renames, undo/redo and new objects, since nothing holds object references across undo (builds on D-018 to D-021). Cached values are plain Python tuples, never live `Vector`/`Euler` objects, so comparing an unchanged property is exact, not approximate — Blender hands back the same floats it was given. |
| D-034: A new object's first appearance enters the cache with no emitted op; a deleted object's ID silently drops out when the cache is rebuilt | There's no `create` or `delete` operation yet (#15 needs mesh data), so sending `set` for an object the other client has never heard of would be meaningless. The cache is rebuilt from a fresh scan each flush, so a removed object simply isn't in the new cache — no explicit delete-handling code needed. |
| D-035: `suppressed()` refreshes the cache from the scene on exit, without emitting | Hook for #6: applying a remote operation must not get diffed back out on the next flush as if it were a local edit. Refreshing the cache (rather than, say, pausing the dirty flag) means the suppressed change is simply the new baseline afterwards. |
| D-036: A Start / Stop detection button in the panel logs each batch as JSON via `log()` | Lets this be tested by hand (and watched in two side-by-side Blenders) before Join room (#13) exists to start detection for real. |
| D-037: `jsonschema` added to `addon/requirements-dev.txt`, installed with `uv pip install` (the venv has no `pip`) | A contract test validates every emitted message against the JSON Schema in `docs/protocol.md` directly, the same guarantee the server side gets from Pydantic (D-029), without needing the schema reimplemented by hand. |

**Details:**
- `_read_object(obj)` returns `{"location", "rotation", "scale", "name"}`; `_read_rotation`
  reads `rotation_euler`, `rotation_quaternion` or `rotation_axis_angle` according to
  `obj.rotation_mode`, matching D-023's `{"mode", "values"}` shape exactly.
- The client Lamport counter and `origin` (D-025) are module state: `origin` is a fresh
  `uuid.uuid4()` each `start()`, `lamport` resets to 0 and then increases by 1 per operation
  (not per batch), so two ops in the same flush still get distinct, ordered timestamps.
- `start()` / `stop()` are idempotent (handler and timer registration is guarded by a
  membership / `is_registered` check, and a module-level `_active` flag), so calling either
  twice in a row is harmless. Handlers and the timer are `persistent=True`, matching the old
  spike handler, so detection survives opening a different `.blend` file mid-session.
- 25 tests in `addon/tests/test_detect.py`: every checklist scenario (single move, no-op
  write, coalesced moves, all three rotation shapes, scale, rename, custom-property no-op,
  new object then a later move, delete, `suppressed()`, Lamport/origin, double `start()`,
  `stop()`), plus a contract test that loads the JSON Schema straight out of
  `docs/protocol.md` (same `_json_blocks()`-style regex as `server/tests/sync/`) and runs
  `jsonschema.validate` on messages from every operation shape.
- Measured scan cost from the issue (0.2 ms / 100 objects, 3.2 ms / 1,000) wasn't
  re-measured here; the design already accounted for it.

**Open / follow-up:** two manual checks are still open before #5 can close — see the message
to Lucas for exactly what to do. Spike-notes' quaternion-rotation item is covered headlessly
by `test_rotation_set_as_quaternion` but stays open until confirmed with a real Rotation Mode
change in the UI. Next: #6 applying remote operations (uses `suppressed()`), #8/#9 on the
server side.

### 2026-10-20 · Fix: pending local edits lost on `suppressed()`; #5 done

Review comment on 48c11ce: a local edit still waiting for its 50 ms tick was being silently
absorbed into the cache when a remote operation was applied inside `suppressed()`, instead
of being sent. Added the repro from the comment as a test, confirmed it failed, then fixed
it. Then ran the two manual checks left open on #5, in Blender 5.2 on 10/20 — both passed.
Closes #5.

| Decision | Why |
|---|---|
| D-038: Entering the outermost `suppressed()` calls `flush()` first (only if `_dirty`) | A dirty-but-unflushed local change and a remote operation applied inside the block both end up as one new cache baseline on exit; flushing first makes sure the local change goes out before that happens, instead of being overwritten by it. |

**Details:**
- `test_suppressed_flushes_pending_local_edits_first` in `addon/tests/test_detect.py`
  reproduces the comment's scenario (object A moved locally, not yet flushed; object B's
  "remote" move applied inside `suppressed()`) and checks A's move was sent and B's wasn't.
- Nested `suppressed()` calls still only flush on the outermost entry (guarded by
  `_suppress_depth == 0`, the same check already used on exit), so #6 applying several
  operations in a row doesn't flush between each one.
- **Manual check, drag / N-panel / quaternion:** orbiting and selecting send nothing;
  dragging sends ~20 batches/second (matches the 50 ms tick); N-panel edits, rotation
  (Euler and Quaternion via the Rotation Mode dropdown), scale and rename each produce the
  right `set` op.
- **Manual check, undo / redo:** undo and redo produce ops back and forth; an object keeps
  its `collab_id` across undo; a Shift+D copy gets a new ID while the original keeps its
  own, including after undo and redo. Moves the matching spike-notes.md items to Resolved.

**Open / follow-up:** D-025's Lamport counter resetting to 0 in `start()` is a separate,
already-noted issue for #8, not fixed here. Next: #6 applying remote operations.

### 2026-10-20 · WebSocket relay: rooms and broadcast (#11)

Built the relay: `ConnectionManager` (`realtime/connections.py`) tracks room membership
and broadcasts; `realtime/websocket.py` is the `/ws/rooms/{room_id}` endpoint, reusing
`parse_message` / `serialize_message` from #7. Added the `error` message and the
forwarding rule to `docs/protocol.md`, and `scripts/ws_probe.py` for testing by hand.
Refs #11 — the issue stays open until the manual check below is done.

| Decision | Why |
|---|---|
| D-039: Rooms are implicit and in-memory — created on the first `join`, removed on the last `leave`; `room_id` must match `^[A-Za-z0-9_-]{1,64}$` or the socket is closed (code 1008) before it's accepted | Matches the minimal prototype scope (#18, real room creation/persistence, is separate). Validating and closing before `accept()` lets a bad `room_id` surface to the client as a failed connection rather than an accepted one that's immediately useless. |
| D-040: An invalid message gets `{"v": 1, "type": "error", "message": "<reason>"}` back on the same connection, which stays open | One bad batch (bad schema, oversized, a stray non-JSON frame) shouldn't cost a client its connection; `parse_message`'s `ValueError` text is reused directly as the reason, so rejections stay specific without a second place to maintain reasons. |
| D-041: Server tests use `with TestClient(create_app()) as client:` (conftest.py), not a bare `TestClient(...)` | A bare `TestClient` gives each `websocket_connect()` call its own `BlockingPortal` (own thread, own event loop); broadcasting between sockets owned by different event loops deadlocked intermittently (~10% of runs, only with 3+ simultaneous connections — reproduced in a minimal FastAPI app with no code of ours involved). Entering the context manager once gives every connection from that client the same portal. Known Starlette behaviour, not a bug in the relay. |

**Details:**
- `ConnectionManager.join` / `leave` / `broadcast` only touch a `dict[str, set[WebSocket]]`;
  `leave` deletes the room once its set is empty. `broadcast` iterates a copy of the set
  (sending can mutate it), excludes the sender (which already applied its own change
  locally, docs/protocol.md rule 8), and drops any socket a send fails on — its own receive
  loop separately notices the disconnect and calls `leave`.
- 8 tests in `server/tests/realtime/test_websocket.py` using `TestClient.websocket_connect`:
  since there's no clean "received nothing" timeout, absence is proved by ordering — e.g.
  to show a client never gets its own message back, a second client sends a second message
  and the test checks *that* arrives first. Each test uses a fresh `uuid4` room id (a `room`
  fixture), so no test can interact with another's sockets even in principle.
- `scripts/ws_probe.py` connects to one room and, on each Enter press, sends the next
  example `ops` message from `docs/protocol.md` (parsed with the same regex trick used in
  `server/tests/sync/` and `addon/tests/test_detect.py`), printing everything it receives.
  Needs the `websockets` package (added to `requirements-dev.txt`; otherwise only an
  indirect `uvicorn[standard]` dependency).
- Verified end-to-end against a real running `uvicorn` server (not just `TestClient`): two
  real `websockets` clients in one room relay correctly, a third in another room gets
  nothing, and a garbage frame gets an `error` without breaking the connection.

**Open / follow-up:** manual check (two probes in one room, one in another) is still open —
see the message to Lucas for the exact commands. `origin` still isn't checked against the
connection that sent it (protocol.md rule 4's last clause); that's auth-shaped work for
#16 / #17, not #11.

### 2026-10-20 · Fix: ruff findings, pin ruff, relay logs weren't showing (#11)

Two review findings on 4884c8d. `ruff check` failed in CI because the local `ruff`
(0.15.12) was older than CI's and missed two rules; and the relay's own log lines never
showed up in the server terminal. Refs #11.

| Decision | Why |
|---|---|
| D-042: `ruff` pinned to `0.17.1` in `server/pyproject.toml` and `addon/requirements-dev.txt`, both venvs reinstalled | So local and CI always run the same rule set; an unpinned `ruff>=0.5` let them silently drift apart. |
| D-043: `create_app()` calls `_configure_logging()`, which gives the `app` logger an INFO-level `StreamHandler` | Uvicorn configures its own loggers but not ours; with no handler in our hierarchy, the root logger's handler of last resort only prints WARNING and above, so `logger.info(...)` in `websocket.py` was silently dropped. Scoped to the `app` namespace, not `logging.basicConfig()` globally, so it doesn't also turn on INFO logging for dependencies. Guarded (`if not app_logger.handlers`) since tests call `create_app()` fresh every time. |

**Details:**
- `connections.py`: `except Exception:  # noqa: BLE001` with a short comment — catching
  everything is intentional (any failed send means the client is gone), so suppressed
  rather than changed.
- `tests/realtime/test_websocket.py`: the one `SIM117` nested-`with` combined (ruff's own
  `--fix`); new `test_connect_is_logged` uses `caplog.set_level(logging.INFO, ...)` and
  checks the connect line's text. 78 server tests pass; `ruff check .` clean in both
  `server/` and `addon/` at the pinned version.
- Verified the fix against a real running `uvicorn` server too: `connect room=... clients=1`
  / `disconnect ...` now print in the terminal, not just under `caplog`.

### 2026-10-21 · Apply remote operations without echo loops (#6)

Added `addon/collaborative_blender/apply.py`: `apply_message` applies one parsed `ops`
message to the local scene, building on `detect.suppressed()` (#5/D-035/D-038) and `ids`
rather than changing either. Added an **Apply from clipboard** dev-aid button. Refs #6 —
the issue stays open until the manual check below is done. `detect.py` only grew a
read-only `origin()` getter; `flush()`/`suppressed()` themselves are unchanged.

| Decision | Why |
|---|---|
| D-044: `apply_message` runs its whole batch inside one `detect.suppressed()` block, looking up `{collab_id: object}` once first | One `suppressed()` call per batch (not per operation) means detect's pending-local-edit flush and cache resync (D-038) each happen once, not once per operation; a single object lookup avoids `ids.find_object`'s scan per operation. |
| D-045: Until #20 syncs room state, both clients must open the same saved `.blend` file, recorded in `addon/README.md` | `collab_id`s are assigned from random UUIDs per session (#4); two independently-opened files give the same object different IDs, so an operation from one would never match anything in the other. IDs are custom properties and so are saved in the file, which sidesteps this for manual testing until real room join exists. |

**Details:**
- `_set_location` / `_set_scale` / `_set_rotation` / `_set_name`, keyed from `property` in
  a fixed dict (never `setattr` with a received name, protocol rule 5). `_set_rotation`
  sets `rotation_mode` before the matching values property, so a mode change and new
  values can never end up mismatched.
- `_apply_op(op, objects, own_origin)` skips (and logs) an op whose `kind` isn't `set`, an
  unknown `property`, an unknown `object`, or an `origin` equal to this client's own —
  never raises. Written as one function, per the issue, so #8/#9 can add an ordering check
  before the setter runs without restructuring the caller.
- `apply_message` itself also tolerates a message that isn't a dict, isn't `{"v": 1,
  "type": "ops", ...}`, or whose `ops` isn't a list — logs and returns rather than raising.
- 15 tests in `addon/tests/test_apply.py`: each property (including both a quaternion and
  an axis-angle rotation, the latter with a mode change), unknown object / kind / property
  skipped without raising a batch that otherwise applies, malformed messages, own-origin
  skip, no echo (`apply_message` then `detect.flush()` sends nothing), the #5 regression
  scenario replayed through `apply_message` instead of `detect.suppressed()` directly,
  last-wins within a batch, every protocol.md example message, and a round trip (a
  message `detect` produced, relabelled to a fake remote origin so the own-origin skip
  doesn't eat it, reproduces the same values on a reset copy of the object).
- **Apply from clipboard** (`operators.py`, `panel.py`): drops everything before the
  clipboard's first `{`, so a line copied straight out of the detection log (with its
  `[collab A HH:MM:SS]` prefix) works unedited; reports a clear error for bad JSON instead
  of raising.

**Open / follow-up:** manual check (two Blenders, same `.blend`, copy a batch from A's
log and apply it in B) is still open — see the message to Lucas for the exact steps,
including preparing the shared file. Next: #12 WebSocket client, which calls
`apply_message` for real instead of the clipboard dev aid.
