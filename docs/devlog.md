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
| Phase | Feature freeze (due 11/16); Prototype done 10/23 |
| In progress | — |
| Next up | #25 Demo prep |
| Done | #1 Repository scaffold, #2 Add-on testing workflow, #3 Change-detection spike, #4 Stable object IDs, #5 Detect local transform changes, #6 Apply remote operations, #7 Operation format, #8 Lamport clock, #9 Last-writer-wins, #11 WebSocket relay, #12 WebSocket client, #13 Join / Leave room, #14 Prototype check, #15 Create / delete sync, #10 Origin validation, #19 Persist the operation log, #23 Server runs from one Docker command, #24 Measure sync latency, #20 Snapshots and catch-up, #16 Accounts and auth tokens, #18 Rooms REST API, #17 Per-room permissions, #21 Convergence tests, #22 Web UI |
| Loose ends | Adjust Last Operation spike item |

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
| D-034 | A new object enters the cache silently (no op for its initial state); a deleted object silently leaves it | 10/20 | Superseded by #15 |
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
| D-045 | Until #20, both clients must open the same saved `.blend` so `collab_id`s already match | 10/21 | Superseded by D-084 / D-085 |
| D-046 | The client Lamport clock (`ordering.LamportClock`) is one shared counter that never resets, not even across `detect.stop()` / `start()` | 10/21 | Active |
| D-047 | Last-writer-wins via `ordering.Versions`: an incoming `set` is applied only if it's newer than the last value this client sent or applied for that key | 10/21 | Active |
| D-048 | `websocket-client` 1.9.2 vendored at `addon/collaborative_blender/vendor/websocket/`, excluded from ruff and pyright | 10/21 | Active |
| D-049 | `client.py` is two daemon threads (reader, writer) that never touch `bpy`; `drain()` is a plain function run by a `bpy.app.timers` tick every ~20 ms | 10/21 | Active |
| D-050 | Reconnect backoff 0.5 s, 1, 2, 4, then every 8 s; the outbox persists across reconnects, capped at 1000 messages (drop the oldest) | 10/21 | Active |
| D-051 | Operations another client sent while this one was disconnected are missed until catch-up (#20) exists | 10/21 | Superseded by D-084 |
| D-052 | `room_id` lives on `WindowManager`, not `Scene`, so it isn't saved into the `.blend` or treated as a scene edit | 10/22 | Active |
| D-053 | Join always runs `detect.stop()` before `detect.start(client.send)`, never just `start()` | 10/22 | Active |
| D-054 | A ~0.25 s main-thread timer compares `client.status()` and `tag_redraw()`s `VIEW_3D` areas only when it changes | 10/22 | Active |
| D-055 | A `load_pre` handler leaves the current room before a different file loads | 10/22 | Active |
| D-056 | Start / Stop detection dev aids (D-036) removed; Join / Leave replace them | 10/22 | Active |
| D-057 | A `set` for an object this client doesn't have is dropped, not buffered | 11/03 | Active |
| D-058 | Objects that can't be sent (non-mesh, too large) stay in the cache, so they're logged once and not retried | 11/03 | Active |
| D-059 | The client's size check measures the whole message with `json.dumps`, as `client.send` does | 11/03 | Active |
| D-060 | Tombstones are cleared when a different file loads | 11/03 | Active |
| D-061 | Incoming geometry goes through `mesh.validate()` | 11/03 | Active |
| D-062 | The newest connection to claim an origin takes it over, rather than being rejected while the old one looks alive | 11/03 | Active |
| D-063 | Origin checks aren't proof of identity: a live client can still claim another's origin until auth exists | 11/03 | Closed by D-094 |
| D-064 | A connection that lost its origin stays open and pinned, getting `error` for anything it sends | 11/03 | Active |
| D-065 | The database engine is built at startup and kept on `app.state`, never at import | 11/03 | Active |
| D-066 | SQLite connections set a 5 s busy timeout, then WAL | 11/03 | Active |
| D-067 | No migrations tool yet: `create_all` at startup | 11/03 | Active |
| D-068 | `seq` uses SQLite AUTOINCREMENT, so it's never reused | 11/03 | Active |
| D-069 | Lamport is capped at 2^63 − 1 in the protocol | 11/03 | Active |
| D-070 | A failed write gets a generic `error` and isn't broadcast or retried | 11/03 | Active |
| D-071 | The container runs as a non-root user, uid 10001 | 11/03 | Active |
| D-072 | One uvicorn worker, explicitly | 11/03 | Active |
| D-073 | Healthcheck in the Dockerfile, using Python's urllib on `/health` | 11/03 | Active |
| D-074 | `docker_smoke.sh` is its own Compose project, with its test client inside the container | 11/03 | Active |
| D-075 | Dependencies install from `pyproject.toml` alone; `app` isn't installed as a package | 11/03 | Active |
| D-076 | The default secret key gets a startup warning, not an error | 11/03 | Active |
| D-077 | Latency timing is out of band, in JSONL files, off by default | 11/03 | Active |
| D-078 | End to end runs from the depsgraph handler to the setter on the receiver | 11/03 | Active |
| D-079 | Across machines: round trip on one clock, with RTT/2 reported alongside a corrected estimate | 11/03 | Active |
| D-080 | Compose passes `COLLAB_TIMING` through, empty (off) by default; latency runs use their own Compose project | 11/05 | Active |
| D-081 | The server folds a room's log with the clients' rules; a `create` also counts as a write of what it carries | 11/05 | Active |
| D-082 | A snapshot every 500 ops (`COLLAB_SNAPSHOT_EVERY`), as a cache over a log that's never trimmed | 11/05 | Active |
| D-083 | One `asyncio.Lock` per room around catch-up and around save → forward | 11/05 | Active |
| D-084 | The server pushes catch-up on every connection, as plain `ops` then `synced`; no request message | 11/05 | Active |
| D-085 | Merge on join: on a Join's first `synced`, offer every local mesh the catch-up didn't mention | 11/05 | Active |
| D-086 | Catch-up batches carry one origin each and stay under 64 KiB | 11/05 | Active |
| D-087 | `client.synced()` sits beside `status()`; inbox entries carry their socket's generation | 11/05 | Active |
| D-088 | Handlers never await the database directly: shielded tasks the app tracks, snapshots counted in memory and written in the background, shutdown ends handlers and that work before disposing the engine | 11/09 | Active |
| D-089 | Passwords hashed with the stdlib's scrypt (n=2^14, r=8, p=1), a salt each, parameters stored with the hash; usernames lowercased | 11/09 | Active |
| D-090 | Login tokens are PyJWT HS256 with `sub` and `exp`, a week by default; no revocation | 11/09 | Active |
| D-091 | The socket's token comes only in the `Authorization` header; accept, then close 4401 / 4403 before catch-up; the add-on stops retrying on either | 11/09 | Active |
| D-092 | Rooms are created before they're joined; roles live only in `room_members`; ids stay human-readable | 11/09 | Active |
| D-093 | Invite codes: shown once, stored as SHA-256, usable by anyone any number of times until they expire (24 h default) or are revoked; joining never lowers a role | 11/09 | Active |
| D-094 | An origin belongs to the first user who sends as it, kept in the database; takeover only by that user (closes D-063) | 11/09 | Active |
| D-095 | Membership changes reach open sockets at once: a removal closes with 4403, a role change applies from the next message | 11/09 | Active |
| D-096 | Convergence is checked against a reference client written from the protocol rules, separate from `RoomState` | 11/09 | Active |
| D-097 | One vector file, `tests/vectors/convergence.json`, generated by the server's tests and replayed through the add-on's real `apply_message` | 11/09 | Active |
| D-098 | 300 fixed seeds in CI, more with `COLLAB_CONVERGENCE_SEEDS`; failures shrink to a replayable trace | 11/09 | Active |
| D-099 | The web UI is built in the server's image and served by FastAPI at `/`, with an SPA fallback that never covers `/api` or `/ws` | 11/09 | Active |
| D-100 | Presence is a REST endpoint over the relay's in-memory connections, polled every 3 s while the room page is visible | 11/09 | Active |
| D-101 | The web UI keeps its token in sessionStorage, not localStorage | 11/09 | Active |
| D-102 | No router or UI library: a small History API router and plain CSS | 11/09 | Active |

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

### 2026-10-21 · Lamport clock and last-writer-wins (#8, #9)

Added `addon/collaborative_blender/ordering.py` (`LamportClock`, `newer`, `Versions`) and
wired it into `detect.py` and `apply.py`, per the single design on #8 (#9 is the
`Versions` half of the same change). Fixes the #5 review note: the client counter no
longer resets on `detect.start()`. Refs #8, refs #9 — both stay open until the manual
check below is done.

| Decision | Why |
|---|---|
| D-046: The Lamport clock is one shared, module-level counter (`ordering.clock`) that never resets, including across `detect.stop()` / `start()` | The original counter reset to 0 on every `start()` (D-025); after a restart, a client's new edits would get lower timestamps than its own earlier ones (or others' recent ones), so last-writer-wins could discard a client's own newest change. `clock.observe(n)` also merges in every timestamp a client receives (`max`), so its own next tick always exceeds anything it has seen. |
| D-047: Last-writer-wins is `ordering.Versions`: a `dict[(collab_id, property), (lamport, origin)]` of the last value sent or applied for that key, checked before applying an incoming `set` | One shared instance for both `detect.py` (records what it sends) and `apply.py` (checks and records what it applies) means an incoming operation is compared against local edits too, not just other incoming ones — the scenario the manual check exercises. |

**Details:**
- `ordering.py` has no `bpy` import, so `LamportClock`, `newer` and `Versions` are plain
  Python, independently testable and reasoned about.
- `detect._make_op` now gets its `lamport` from `ordering.clock.tick()` and records
  `(collab_id, property) -> (lamport, origin)` via `ordering.versions.record`, instead of
  its own counter. `start()` no longer touches any counter at all.
- `apply._apply_op`, for each `set` that passes the existing kind/property/object checks:
  `ordering.clock.observe(op["lamport"])`, then `ordering.versions.should_apply(key,
  op_id)` before running the setter; skips (and logs `apply: skip, older than local`)
  otherwise. The setter call is now also wrapped in `try`/`except`, logging and skipping
  rather than raising, since a schema-valid value can still be one Blender rejects
  (follow-up noted on #6).
- `docs/protocol.md` rule 1 now describes the client-side check and the clock's merge
  rule, rather than just saying "Implemented in #8 and #9".
- Tests: `test_ordering.py` (6, plain Python: tick, observe + a following tick, tie
  breaking, `should_apply` for an unknown / newer / older / equal key); `test_convergence.py`
  (10 seeds, plain Python: 3 replicas apply the same randomly-generated operations each in
  their own shuffled order and end up identical); 1 new case in `test_detect.py` (the
  clock keeps counting up across `stop()`/`start()`) and 4 in `test_apply.py` (newer
  applied, an older local-then-remote case, a Lamport tie decided by origin, a setter
  exception not aborting the rest of the batch). Existing `test_apply.py` cases needed one
  fix: the round-trip test replays a message `detect` itself just emitted (and so already
  recorded a version for), so relabelling only its `origin` could tie against that record
  depending on random origin ordering — it now also bumps the lamport, matching what an
  actually-newer remote batch would look like. 71 add-on tests pass; `ruff check .` clean.

**Open / follow-up:** manual check (two Blenders, same `.blend` as #6's workaround) is
still open — see the message to Lucas for the exact steps. Server-side counterparts
(`server/app/sync/clock.py`, `conflicts.py`) wait for the operation log (#19) and
convergence tests (#21).

### 2026-10-21 · Add-on WebSocket client (#12)

Vendored `websocket-client` and added `addon/collaborative_blender/client.py`, connecting
#5/#6 to the relay (#11). No Join / Leave buttons yet (#13); driven from the Python
console for now. Refs #12 — stays open until the manual check below is done.

| Decision | Why |
|---|---|
| D-048: Vendor `websocket-client` 1.9.2 at `addon/collaborative_blender/vendor/websocket/` (`LICENSE` and `vendor/README.md` included; excluded from `ruff` and the type checker) | Blender's Python has no WebSocket library and add-ons can't rely on users running `pip install`. `websocket-client` is pure Python with no required dependencies and all-relative internal imports, so `from .vendor import websocket` needs no `sys.path` change and can't clash with another add-on's own copy. Rejected: `websockets` (asyncio, would need an event loop in a thread, fighting the design below); a hand-written client (framing, masking and ping are easy to get wrong). Verified by hand against the real relay from Blender 5.2's Python first (sends arrive at another client's reader; sending still works while that connection's reader is blocked in `recv()`; `close()` stops the reader in ~1 ms; a down server raises `ConnectionRefusedError`; after `close()`, `recv()` returns `""` instead of raising). |
| D-049: `client.py` is two daemon threads — a reader (blocking `recv()` into an inbox queue) and a writer (an outbox queue into `send()`), which also owns the connect / reconnect lifecycle; `drain()` is a plain function a `bpy.app.timers` tick calls every ~20 ms | `bpy` is only safe on the main thread, so the threads never touch it; they only move text through queues. `drain()` being plain (not the timer callback itself) lets headless tests call it directly, the same reason `detect.flush()` is one (#5). |
| D-050: Reconnect backoff 0.5 s, 1, 2, 4, then every 8 s; the outbox persists across reconnects, capped at 1000 (drop the oldest, logged) | A dropped connection should retry promptly at first without hammering a server that's actually down for a while. Keeping the outbox means a brief blip doesn't lose anything typed/moved during it; the cap keeps a long outage from growing memory without bound. |
| D-051: Operations other clients sent while this one was disconnected are missed until catch-up (#20) exists | No message log to replay from yet; `join` doesn't carry a last-seen Lamport either (#11's `join` row in protocol.md is still TODO). Noted here rather than solved, matching the issue. |

**Details:**
- `connect(server_url, room_id, on_message)` checks `room_id` against the same pattern
  the server enforces (`^[A-Za-z0-9_-]{1,64}$`) and raises `ValueError` synchronously,
  before touching the network, for one the relay would refuse anyway (#11); otherwise it
  returns immediately and the actual connection happens on the writer thread.
- `send(message)` serializes to JSON and appends to the outbox; never blocks.
- `disconnect()` signals both threads to stop, closes the socket (which wakes a reader
  blocked in `recv()`), joins the writer (which itself joins its current reader before
  returning), and unregisters the timer. Idempotent, like `detect.stop()`.
- `status()` reads `"disconnected"` before any `connect()` or after `disconnect()`,
  `"connecting"` for the very first attempt, `"connected"` once it succeeds, and
  `"reconnecting"` for every attempt after a failure or a drop — including the first
  attempt against a server that's down, so it never gets stuck reporting `"connecting"`
  forever.
- `drain()` parses each inbox message as JSON; an `ops` message goes to `on_message`
  (intended to be `apply.apply_message`, passed in by the caller — `client.py` doesn't
  import `apply` itself); an `error` message or invalid JSON is logged and stops there.
- `unregister()` in `__init__.py` now also calls `client.disconnect()`, alongside
  `detect.stop()` (#4).
- 8 tests in `addon/tests/test_client.py` against a small fake relay (`websockets`,
  added to `requirements-dev.txt` for tests only) run on a background thread with its
  own event loop: connects to `"connected"`; `send()` arrives as JSON; a server message
  reaches `on_message` only after `drain()`, and on the thread that called it (recorded
  and compared inside the callback); `error` / invalid JSON are logged (checked via
  `capsys`, since `log()` is a `print`, not `logging`) and never reach `on_message`;
  stopping the fake server gives `"reconnecting"`, and restarting it on the same port
  reconnects and delivers a message queued while it was down; connecting to a dead
  server (`ws://localhost:1`) doesn't raise; `disconnect()` leaves no new threads in
  `threading.enumerate()`; a bad room id raises before anything connects. One fake-relay
  bug found along the way: `FakeRelay.stop()` wasn't idempotent, and the reconnect test
  calls it manually before the fixture's own teardown calls it again — fixed with a
  `_stopped` flag. 79 add-on tests pass; `ruff check .` clean (vendor/ excluded).

**Open / follow-up:** manual check (real server, a Blender connected from the Python
console, `ws_probe.py` in the same room) is still open — see the message to Lucas for
the exact steps. Next: #13 Join / Leave room buttons wire `client.connect` /
`client.send` / `apply.apply_message` together behind the panel, instead of the console.

### 2026-10-21 · #12 manual check passed

Lucas ran the real relay, connected Blender from the Python console and ran `ws_probe.py`
in room `demo`. Moving the cube reached the probe; the probe's example message reached
Blender (`apply: skip, unknown object`, expected); stopping and restarting the server
went `reconnecting` → `connected`. Gotcha found: `detect.start()` is a no-op if the panel's
dev-aid detection is already running (it logs instead of sending), so stop it first. #13
removes that trap by having Join room start detection with `client.send`. #12 closed.

### 2026-10-22 · Wire up Join room / Leave room (#13)

Join room and Leave room now do for real what the #12 manual check did from the Python
console: connect/disconnect the client, start/stop detection, and show live status.
Removed the Start / Stop detection dev aids (Join replaces them). Refs #13 — stays open
until the manual check below is done.

| Decision | Why |
|---|---|
| D-052: `room_id` is a `StringProperty` on `bpy.types.WindowManager`, default `"demo"`, not on `Scene` | A `Scene` property would be saved into the `.blend` and (per #5/D-033) setting it might register as something detection has to think about. Window-manager state is exactly "this session, this room" and nothing more. |
| D-053: Join always calls `detect.stop()` before `detect.start(client.send)`, never `start()` alone | `start()` is a no-op while already active (#5's idempotency guard) — if the old dev-aid detection (or a previous room) left it running, a bare `start()` would silently keep sending to whatever `send` callback was already wired up (the terminal log) instead of `client.send`. This is the exact trap the #12 manual check hit by hand. |
| D-054: A ~0.25 s main-thread timer compares `client.status()` to its last-seen value and calls `tag_redraw()` on every `VIEW_3D` area's `UI` region only when it changes; registered by Join, unregistered by Leave | `client.status()` changes on a background thread (#12), and Blender only redraws a panel on mouse hover, so without this the status line would look frozen. The timer only ever reads `status()` — never the socket — keeping the "threads never touch `bpy`" rule from #12 intact. |
| D-055: A `load_pre` handler runs the same Leave logic before a different file loads | Detection's cache and the scene's `collab_id`s belong to the file being replaced; staying connected across a file switch would mean sending operations for objects that, from the room's perspective, no longer exist. |
| D-056: Start / Stop detection (D-036) removed; `panel.py` and `operators.py` lost those buttons and operators | They're exactly what Join now does, correctly (D-053) — keeping both around is what caused the #12 trap. `detect.is_active()`, now unused, was removed too. |

**Details:**
- `COLLAB_OT_join_room.poll()` requires `client.status() == "disconnected"`; `execute()`
  reads the server URL from `preferences.addons[__package__].preferences.server_url`
  (already existed) and the room id from `window_manager.room_id`, calls
  `client.connect(...)`, catches `ValueError` from an invalid room id (`self.report`,
  `{"CANCELLED"}`, nothing started), otherwise does D-053's stop-then-start and starts
  the status-watch timer. `COLLAB_OT_leave_room.poll()` requires status `!=
  "disconnected"`; both it and the new `_on_load_pre` call one shared `_leave_room()`
  function (`detect.stop()`, `client.disconnect()`, stop the status-watch timer).
- Panel: the room field is in a `row.enabled = (status == "disconnected")` row, so it's
  greyed out while connecting / connected / reconnecting; the status line reads from a
  `_STATUS_TEXT` dict keyed by `client.status()`, formatted with the room name, matching
  the issue's table exactly (`"Not connected"`, `"Connecting to {room}…"`, …).
- 6 tests in `addon/tests/test_join_leave.py`, against #12's fake relay (moved from
  `test_client.py` into `conftest.py` as `FakeRelay` / `wait_until`, now shared by both
  files): Join connects, starts detection, and a moved object reaches the relay; an
  invalid room id raises (Blender re-raises an operator's `self.report({"ERROR"}, ...)`
  as a Python `RuntimeError` when called via `bpy.ops` from a script, so the test catches
  that) and nothing started; Leave disconnects and stops detection; Join while detection
  was already running still sends (the regression test for D-053); the `load_pre` handler
  is registered and leaves the room; the status-text table.
- Bug found writing these tests, not in the production code: a test file's own
  `from collaborative_blender import X` at module level binds once, at collection time,
  to whichever module objects exist then. `conftest.py`'s `addon` fixture drops and
  re-imports the package fresh for every test (so Blender's own registration stays
  clean), so that module-level binding goes stale after the first test — fine for tests
  that only ever call plain functions (`detect.flush()`, consistently against that same
  stale copy), but not here, since `bpy.ops.collaborative.join_room()` runs the
  *currently registered* operator, which calls into the *current* `client` / `detect`.
  Checking a stale copy's `client.status()` afterwards just watches the wrong object
  forever. Fixed by reading everything off the `addon` fixture's return value
  (`addon.client`, `addon.detect`, ...), which is always the module actually in effect.
- `addon/README.md`'s manual-sync section now describes joining a room with both
  clients instead of starting the old dev-aid detection.

**Open / follow-up:** manual check (one Blender, buttons only, `ws_probe.py` in the same
room) is still open — see the message to Lucas for the exact steps. Next: #14, the first
full two-Blender prototype check with everything built so far.

### 2026-10-22 · #13 manual check passed

Lucas ran one Blender (buttons only) with `ws_probe.py` in room `demo`: the status line
updates by itself (Connecting → Connected → Reconnecting → Connected across a server
restart), moves reach the probe and the probe's message reaches Blender, Leave stops
sending, an invalid room id shows an error and stays disconnected, and File › New leaves
the room. #13 closed.

### 2026-10-23 · Prototype milestone done (#14)

Lucas ran the two-Blender check on `shared.blend` in room `demo`: move, rotate, scale,
rename, typed N-panel values and undo all sync both ways; simultaneous edits to one object
converge; no echo; Leave / rejoin and a server restart recover. Known limits confirmed, as
expected: added or deleted objects don't sync (#15), and edits made while disconnected aren't
caught up (#20). Demo video recorded for the submission. Prototype milestone closed a day
early.

Planning for Feature freeze: #10 moved from Prototype to Feature freeze (it wasn't needed for
the two-Blender check; the relay already validates schema and size). Next batch, with
designs in the issues: #15 (create / delete, including a new ID for objects brought back by
undo, so tombstones stay correct), #10 (pin `origin` per connection), #19 (SQLite operation
log, with the server's arrival `seq` as the catch-up cursor). #20 builds on #15 and #19 and
removes the shared-`.blend` requirement (D-045).

### 2026-11-03 · Sync object create and delete (#15)

Adding, duplicating and deleting mesh objects now syncs. `flush()` sends a `create` for an ID
it hasn't seen and a `delete` for one that's gone, replacing D-034; `apply.py` rebuilds and
removes objects. Deleted IDs are tombstoned in one set in `ordering.py`, and an object brought
back by Cmd+Z gets a new ID. Refs #15: stays open until the manual check is done.

| Decision | Why |
|---|---|
| D-057: A `set` for an unknown object is dropped, not buffered (protocol rule 9) | A sender's `create` always goes first over one ordered connection, so only a client that missed the `create` sees this, and buffering wouldn't help: #20 has to recover that client anyway. A buffer would also need a timeout and a size limit. Rejected: buffering briefly. |
| D-058: Non-mesh and too-large objects stay in the cache | Otherwise they'd look new on every flush, retrying and logging forever. Side effect: their `set`s and `delete` are still sent. Receivers without the object skip the `set`s, and a `delete` there just records a tombstone. Objects from the shared `.blend` (a camera, say) do exist on both sides, so their `delete` has to keep working. |
| D-059: The size check measures the whole message with `json.dumps` | That's exactly what `client.send` puts on the wire and the relay measures, so the two can't disagree. A server test finds the largest `create` that fits and confirms the relay accepts it. |
| D-060: `_on_load_pre` clears tombstones | Found while designing this: with D-045's shared `.blend`, reopening the file legitimately brings a deleted object back under its old ID. If the tombstone survived, the first flush would re-ID it on both clients and send two `create`s, duplicating it. |
| D-061: `apply` calls `mesh.validate()` on incoming geometry | The schema checks that face indices are in range but allows a face like `[0, 0, 1]`, and geometry from the network is untrusted. It leaves valid meshes unchanged. |

**Details:**
- `flush()` returns only the `set` / `delete` batch; a flush that only sends `create`s returns
  None. Existing tests that assumed a silent add now clear `sent` after the first flush.
- `_retire_tombstoned_ids()` runs at the start of `flush()`, and also removes the old ID from
  the cache so no second `delete` goes out. Join's snapshot stays silent, so an object undeleted
  while out of the room is picked up by the first flush after joining.
- Verified headless, in one-off scripts: removing an object in Edit Mode is safe (Blender drops
  to Object Mode); real `primitive_*_add`, `duplicate_move`, `duplicate_move_linked`,
  `object.delete` and `ed.undo` behave as designed, and those `create`s pass the server's
  `parse_message`. A UV sphere (482 vertices) or Suzanne is about 26 KB.
- The server already validated `create` / `delete` and the size limit (#7 / #11), so it only
  gained tests. Mutation-checked: breaking each tombstone, idempotency, size and non-mesh rule
  in turn makes a test fail.

**Open / follow-up:**
- Manual check (Lucas): see the PR.
- **Undo reaches other people's objects.** Blender's undo restores the whole scene, and rule 7
  sends whatever differs. Confirmed headless: with a remote object applied since the last undo
  step, Cmd+Z removes it locally and sends a `delete`, so it's gone for everyone, permanently.
  `set`s already behaved this way, but a delete can't be undone by anyone else. Needs a decision.
- Batches aren't split: a `set` / `delete` batch over 64 KiB (roughly 500 deletes at once) is
  rejected whole by the relay, and the sender has already tombstoned those IDs, so they diverge.
- Prompt items that depend on later issues: op log (#19), tombstones in server state and
  server-side catch-up (#20), room permissions (#16 / #17). Only the client half of catch-up is
  tested so far (replaying a missed `create` + `delete`).
- Loose edges aren't sent (no `edges` in the schema), so a Circle arrives as bare vertices.

### 2026-11-03 · Validate incoming operations (#10)

The relay now checks `origin`: every op in a message must share one, and `OriginRegistry`
(`validation.py`) pins a connection to its origin on its first valid message. A rejected message
gets the usual `error` reply (D-040), isn't relayed, and the connection stays open.

| Decision | Why |
|---|---|
| D-062: The newest connection to claim an origin takes it over; the issue's plain "reject if another live connection has it" isn't used | The race is real. `room_socket` only learns a client left when `receive_text()` raises, which after a drop with no FIN waits for uvicorn's keepalive (default 20 s ping + 20 s timeout), while the add-on reconnected in under 0.1 s with the same origin. Measured with the real `client.py`, real uvicorn and a proxy that cuts only the client side: the server counted the old socket as connected, and plain rejection lost the reconnected client's edit (`error`, nothing relayed). The add-on only logs an `error`, so edits would vanish for up to ~40 s. Takeover relayed it. Rejected: an idle-time threshold (a client can reconnect milliseconds after its last send, and an idle live client looks stale). |
| D-063: Takeover can't tell a reconnect from a spoof, and nothing here stops a second live client claiming an origin | Said plainly: **a client can copy an origin off any relayed op, send as it, and lock the real client out.** This closes accidental misuse and one connection hopping between origins, not deliberate impersonation within a room, and any client can join any room today. Only auth can fix it: tie an origin to a user (#16 / #17) and allow takeover only by the same user. Rejected for now: a liveness ping to the old connection before takeover, which needs a new message type and an add-on change (the issue says the add-on is unaffected), holds up the new connection's first message, and still proves nothing about who's asking. A takeover logs a `WARNING` so it's at least visible. |
| D-064: The connection that lost an origin stays open and pinned; the server doesn't close it | Follows D-040, and a stale socket gets cleaned up by keepalive anyway. It can't claim the origin back or move to another, so one connection can't ping-pong. Rejected: closing it. The add-on auto-reconnects, so a spoofer and its victim would kick each other in a loop, and awaiting a close on a half-open socket can stall the relay on the close handshake. Cost: a real client locked out by a spoofer stays locked out until it rejoins, with only a terminal log line. |

**Details:**
- `check` raises `ValueError`, so origin rejections use the same `except` as `parse_message` and
  one error path. An invalid message never pins, because parsing runs first.
- `release` only frees the origin if that connection still holds it. Otherwise a stale socket
  found dead 40 s later would free an origin the reconnected client is using, and that client's
  next message would be refused.
- Connections are keyed by `id(websocket)`, safe because `room_socket` keeps the socket alive
  until after `release` runs in `finally`.
- Mutation-checked: breaking each rule makes the suite fail, though three of them fail by hanging
  a relay test (`receive_text` has no timeout), not with a clean assertion.

**Open / follow-up:**
- Tie origins to users when auth lands (#16 / #17), which closes D-063.
- A message still in flight on the old socket when a takeover happens is refused, and nobody is
  left to see the `error`, so that edit is lost. It needs the old socket's message to be processed
  after the new one's, which is unlikely since it arrived first.
- #19: append to the log only after these checks, so rejected messages are never logged.

### 2026-11-03 · Persist the operation log (#19)

The relay now saves every valid message before broadcasting it: parse → `origins.check` → append
→ broadcast. History lives in one SQLite table, `operations`, and survives a restart. Rooms and
who's connected are still in memory (D-039). `scripts/show_log.py` prints a room's log. The manual check below is still open.

| Decision | Why |
|---|---|
| D-065: The engine is built in the FastAPI lifespan and kept on `app.state`; `create_app(database_url=None)` can override the URL | `app.main` builds an app at import, so a module-level engine would point every test at the same database, and the restart test needs two apps on one file. `session.py` holds only factories. |
| D-066: SQLite connections set `busy_timeout=5000`, then `journal_mode=WAL` | Timeout first, because switching to WAL needs a lock itself. WAL is what adds value: `show_log.py` can read while the server writes, and writes don't wait for readers. The timeout mostly makes explicit what Python's `sqlite3` already does, 5 s by default. Measured: with the timeout forced to 0 the concurrency test hits a real `database is locked`, and with both pragmas removed it still passes on that default. Writers still go one at a time: 4 writers × 250 messages through real uvicorn took 0.63 s with no errors. |
| D-067: No migrations tool; `create_all` at startup | One table that may still change, and no data worth keeping yet. `create_all` never alters an existing table, so a column change means deleting the database. Add Alembic when the schema starts changing with data worth keeping. |
| D-068: `sqlite_autoincrement` on `seq` | A plain SQLite rowid can reuse the numbers of deleted newest rows. A reused `seq` would make a client's "everything after N" skip rows silently once #20's compaction deletes any. |
| D-069: `lamport` is at most 2^63 − 1 (schema, model and protocol.md) | The spec had no upper limit, but a 64-bit column does, so an absurd value would pass validation and then fail as a database error. Now it's rejected as invalid. `lamport` is `BigInteger` so Postgres would hold the same range. |
| D-070: A failed write gets a generic `error`, with details only in the server's log; no broadcast and no retry | Nothing may be broadcast that isn't in the log, and database errors can include SQL and paths. Cost: the sender has already applied its edit and the add-on only logs `error`, so that client differs from the others until #20 gives it a way to recover. A write can fail this way if the disk is full, or if another process holds the lock past the 5 s timeout. |

**Details:**
- `pyproject.toml` now asks for `sqlalchemy[asyncio]`. SQLAlchemy 2.1 makes `greenlet` optional and
  async mode fails without it, so a fresh install, CI or Docker would have broken at runtime.
  **Re-run `pip install -e ".[dev]"` after pulling.**
- `append` commits and rolls back explicitly rather than using `session.begin()`, which raises if
  a `since` on the same session has already started a transaction. #20 is likely to do that.
- `since` clamps `limit` to 0..1000, because SQLite reads a negative LIMIT as "no limit".
- `show_log.py` adds `server/` to its import path, since running a script only puts `scripts/`
  there and the editable install didn't make `app` importable (the repo path has a space, which
  may be why; not confirmed).
- `.gitignore` had `server/data/`, which covers a server started from `server/`. Changed to `data/`
  so starting it from anywhere else is covered too, including the `-wal` and `-shm` files that
  `*.db` wouldn't match.
- Created `server/README.md`, which didn't exist.
- Verified with a one-off run: real Blender operators through real `detect` and `client.py` into
  real uvicorn, then `kill -9`, restart and `show_log.py`. All rows survived, including the last
  ones written.
- Mutation-checked. One of my tests failed this check: the original "saved before broadcast" test
  passed with the order reversed, because the write finished before the test looked. It's replaced
  by a test that reads the log from inside the broadcast. Two other mutants (no append at all, and
  an inclusive `after_seq`) are caught only by a hang: `receive_text` has no timeout, and the
  `show_log.py` loop never ends if `since` repeats a row.

**Open / follow-up:**
- Manual check (Lucas): Blender edits in room `demo`, restart the server, `show_log.py demo`.
- #23: `docker-compose.yml` already puts `/srv/data` on a volume and `WORKDIR /srv` makes `./data`
  land there, so this should already work, but it hasn't been run in Docker.
- #24 should measure the write-before-broadcast latency. Rough number from one run on this Mac:
  A→B median 0.67 ms, p99 1.02 ms with small `set`s on an idle machine, with no before/after
  comparison and no large meshes.
- #20: `seq` order matches commit order on SQLite, which has one writer at a time. On Postgres a
  sequence value can commit out of order, so "everything after N" could miss rows. Revisit before
  switching (D-004).
- A client's send retry after a failed connection can log the same operation twice, because
  (`lamport`, `origin`) has no unique constraint. Replaying it is harmless since operations are
  idempotent, and a constraint would turn a retry into a failed write and an `error`.
- The log grows without limit until #20's compaction, and a large `create` is up to 64 KiB a row.

### 2026-11-03 · Server runs from one Docker command (#23)

`docker compose up --build` now gives a non-root, single-worker, health-checked server whose data
survives restarts, and `scripts/docker_smoke.sh` proves it from a clean build. Before the changes
it already started and stopped cleanly, but it ran as root and `show_log.py` wasn't in the image.

| Decision | Why |
|---|---|
| D-071: The container runs as `collab`, uid 10001; `/srv/data` is created and chowned before `VOLUME` | A fresh named volume copies the ownership of the folder it mounts over, so a brand-new volume is writable with no entrypoint script. Cost: a volume first created by the older root image stays root-owned, and the server restart-loops on `unable to open database file` until `down -v`. Accepted, since no data worth keeping exists yet; it's in the README. |
| D-072: `--workers 1`, with a comment saying why | Rooms and origin pins are in-process memory, so a second worker would split a room in two with no error. SQLite's single writer points the same way. Scaling out would need shared room state first. |
| D-073: `HEALTHCHECK` in the Dockerfile, with `python -c` and urllib | The slim image has no curl, and installing it for this isn't worth a layer. In the Dockerfile rather than compose, so a plain `docker run` gets it too. `--start-interval=1s` makes startup report healthy in about a second. `/health` doesn't touch the database, so it means "the process answers": a database that won't open is still caught, because startup fails and the container exits, but a disk that fills up later isn't. |
| D-074: `docker_smoke.sh` runs as Compose project `collaborative-smoke`; `smoke_client.py` runs inside the container | The script runs `down -v`, which would delete real data under the default project name. Inside the container, the client needs nothing on the host but Docker and curl, so it works on a clean machine and in CI. `ws_probe.py` didn't fit: it waits for Enter and reads `docs/protocol.md`, which isn't in the image. The published port is covered by `curl` on `/health` in the script and by the add-on run. |
| D-075: The dependency layer reads `pyproject.toml` with `tomllib`; `app` runs from `/srv` | A code edit now rebuilds in under a second with the `pip install` layer cached. It also removes the unused second copy of `app` in site-packages and the stray `build/` folder. |
| D-076: A `WARNING` at startup while `COLLAB_SECRET_KEY` is the default | Enforcing it is #16. Logged in `lifespan`, so building the app (as importing `app.main` and every test does) stays quiet. |

**Details:**
- `.dockerignore` patterns only match at the top level without `**/`, so local `__pycache__` folders
  were being copied into the image. Fixed.
- `docker compose stop` with a client connected takes at most about a second, with exit code 0.
  Uvicorn closes the socket with code 1012, so the 10 s kill is never reached.
- `.env` next to `docker-compose.yml` works through Compose's own variable substitution, so an
  absent file is fine. The server's own `.env` reading isn't involved, since `.dockerignore`
  keeps `.env` out of the image.
- `restart: unless-stopped` checked: SIGTERM from inside brings it back, `compose stop` doesn't.
- CI runs the whole smoke script rather than only `/health`, since that was one line more.
- Verified with two real Blender 5.2.2 windows, using the default Server URL and scripted real
  operators (`primitive_cube_add`, `transform.translate`): create and moves in both directions,
  then a `docker compose restart` underneath them. Both reconnected in about 3 s and the next move
  synced. `show_log.py` listed all four operations.
- Mutation-checked the smoke script: root, no scripts, no healthcheck, no volume, no warning and an
  ignored SIGTERM each fail it. The check also exposed a bug in the script: `logs | grep -q` under
  `pipefail` can fail at random when `grep` quits early, so it now matches on captured output.

**Open / follow-up:**
- Not run: a second physical machine on the LAN (the LAN IP was only tried from the host), and
  the first CI run, which needs a PR. Only built for arm64 here; CI will be the first amd64 build.
- Mouse-driven edits in the Blender windows: the run above used scripted operators (Lucas's check).
- Dependencies are `>=` ranges with no lock file, so a future clean build can get different
  versions and break. Worth a lock file before the demo.
- #16: enforce the secret key, and until then anyone who can reach port 8000 can join any room.
- #22: the web service placeholder in `docker-compose.yml`.

### 2026-11-03 · Measure sync latency (#24)

Added out-of-band timing on both sides and tools to run real Blender scenarios and join the results.
On one machine everything is well under 200 ms: worst p95 92.6 ms, worst sample 106.9 ms. About 97% of
the time is timers. The LAN run, which the criterion actually asks about, is still open. Results and
method are in [latency.md](latency.md).

| Decision | Why |
|---|---|
| D-077: `COLLAB_TIMING=<file>` turns on per-process JSONL, keyed by (`origin`, `lamport`, `object`); marks go to a buffer and a background thread writes them | The schema forbids extra fields, and changing the protocol to measure it would be wrong. The buffer keeps file I/O off the measured path: about 160 ns per mark. Off, there's no clock read and no file, just a no-op call of about 50 ns. The add-on and server each have their own module, because the add-on ships alone. |
| D-078: End to end is first depsgraph handler call since the last flush → setter done on the receiver, split into ten stages | As specified, with one change: there are three timers, because the writer thread also sleeps `DRAIN_INTERVAL` when idle, so it gets its own stage. `applied` isn't visible, so the driver also records viewport draws, as a separate row (p95 under 7 ms in all runs). |
| D-079: Across machines, measure a round trip on A's clock and report RTT/2 plus local end to end + (LAN RTT − same-machine RTT) / 2 | Clocks don't agree across machines. RTT/2 alone understates the system because the probe has no Blender timers: 26 ms against 58 ms measured on one machine. The estimate assumes timers don't change with distance. |

**Details:**
- `scripts/latency_run.py` starts the server, two Blenders and any load; `latency_blender.py` drives
  them; `latency_report.py` joins the files; `latency_load.py` and `latency_probe.py` are the simulated
  clients. Raw data goes to `latency-results/`, git-ignored.
- `INTERVAL` and `DRAIN_INTERVAL` are unchanged.
- The first drag run produced zero samples and still printed `ok`: a simulated G key doesn't reach the
  keymap. The driver now invokes the modal directly and checks it started, and the runner fails on zero
  samples. That guard then caught a mistake in my own RTT test.
- Blender saves `quit.blend` in the system temp folder on exit, so automated runs overwrite Recover Last
  Session. The runner now points `TMPDIR` elsewhere; the earlier #23 run did overwrite it once.
- Mutation-checked the report and hooks; two mutants survived at first (a clock stuck at a constant, and
  the reply's origin check), so tests were added for both.

**Open / follow-up:**
- Lucas: scenario 5 over the LAN, with the steps in latency.md. Then `Closes #24`.
- Scenario 6 (Docker) after #23 merges.
- The idle detect wait reaches about 67 ms rather than 50 ms. Reproduced, not explained; see latency.md.
- Optional: waking the writer with a `threading.Event` would save about 11 ms at p50, with less CPU.
- Nothing here measured the server's capacity: 160 msg/s was simply fine.

### 2026-11-05 · LAN and Docker latency; #24 done

Lucas ran scenario 5 over home Wi-Fi with an iPhone as the far end: round trip p50 130.7 ms, p95
201.3 ms. The estimated end to end is 97 ms at p50, **151 ms at p95** and 176 ms at p99, so the
criterion is met with about 50 ms to spare rather than 100, and the slowest samples are probably over
200 ms (about 227 ms at the maximum). Scenario 6, against the Docker server on this Mac, gave p95
94.0 ms, about 5 ms more than native. Both are in [latency.md](latency.md).

| Decision | Why |
|---|---|
| D-080: `docker-compose.yml` passes `COLLAB_TIMING` through, empty by default; latency runs use Compose project `collab-latency` and end with `down -v` | An empty value means off in `timing.configure`, so a normal `docker compose up` is unchanged. A separate project keeps the run's ops and timing file out of the real `server-data` volume, as D-074 does for the smoke test. |

**Details:**
- Fixed `latency_probe.py`: with websockets 17, `websockets.exceptions` only loads once a connection
  is made, so `--help`, a missing argument or a refused connection all ended in an `AttributeError`
  that hid the real error. It now imports `ConnectionClosed` explicitly, and a failed connection prints
  the `OSError` (for example "No route to host") and exits 1. Three subprocess tests cover it and fail
  without the fix.
- The LAN steps now cover a phone as machine 2 (a-Shell or Termux): curl from
  raw.githubusercontent.com, Smart Punctuation off, no tab completion, Local Network access, and
  starting the probe only once `latency_run.py` waits at its prompt.
- In Docker the SQLite commit takes 4.7 ms at p50, against 1.0 ms natively, since the database is on a
  volume inside Docker Desktop's VM. That accounts for most of the difference.

**Open / follow-up:**
- The LAN figure is an estimate from a round trip to a phone in Low Power Mode, likely pessimistic.
  A laptop-to-laptop or Ethernet run would tighten it, but isn't needed for the criterion.
- The tail over Wi-Fi is the closest thing to the target. If it matters for the demo, the writer's
  `threading.Event` (about 11 ms at p50) is still the cheapest gain; `INTERVAL` and `DRAIN_INTERVAL`
  are unchanged.
- The idle detect wait above 50 ms is still unexplained.

### 2026-11-05 · Snapshots and catch-up after reconnect (#20)

Every new connection now gets the room's current state before any live traffic: the server
folds its log (latest snapshot + the rows after it) with the clients' own rules, and sends the
result as ordinary `ops` messages followed by `{"type": "synced", "seq": N}`. A Blender with an
empty scene gets every object, one that was away gets what it missed (deletes included), and
on a Join's first `synced` the add-on offers the room any local mesh it doesn't know. Two
Blenders no longer need to open the same `.blend`, so D-045 and D-051 are superseded. Snapshots
are written every 500 ops, and `GET /api/rooms/{id}/snapshot` and `/operations?since=` read the
same state.

| Decision | Why |
|---|---|
| D-081: `RoomState` (`server/app/sync/conflicts.py`) folds ops with protocol rules 1–3: per (object, property) the highest (lamport, origin) `set` wins; the first `create` per ID wins; a `delete` tombstones the ID, drops its create and sets, and beats every later op. Two additions: **a `create` counts as a write of `location`, `rotation`, `scale` and `name` at its own op ID**, so an older `set` loses, and of several deletes for one ID the oldest is kept. The add-on follows the first one too: `detect` and `apply` record `Versions` for a create. | The same rules as the clients, so the state the server sends is what clients that saw every op already have. Without the create rule, merge on join breaks: a client that edits an object during catch-up sends `set`s the room drops (rule 9), then offers the object with a newer `create`. A later joiner would apply the stale `set` over the `create`. Keeping the oldest delete makes the state independent of arrival order, which 200 random sequences check. Live, every remote `set` is already newer than the `create` its sender saw, so nothing else changes. A `set` for an object the log never created is kept, because logs from the shared-`.blend` era have them. |
| D-082: A snapshot is written after an append once the room's log has grown `COLLAB_SNAPSHOT_EVERY` ops (500) past its latest one: latest snapshot + fold of the rows since. `snapshots` holds (room_id, seq, state JSON, created_at). Log rows are never deleted. A failed snapshot is only logged. | A snapshot is a cache: it bounds how much of the log a join has to fold. The operation history is a success criterion, so nothing is trimmed (compaction is a follow-up). Measured here: a snapshot write costs 6–9 ms for a 200-object room, once every 500 ops, and the "not due yet" check costs about 0.5 ms per message, all after the broadcast. The op is already saved and relayed, so a failed snapshot costs nothing but a longer fold next time. Rejected: a snapshot on a timer, which would need a background task per room. |
| D-083: One `asyncio.Lock` per room, held around "join → read state → send catch-up → `synced`" and around "append → broadcast → snapshot check". The locks live on `app.state`, not in the module. | Without it, a live op can land between reading the state and joining (lost) or reach a client before its catch-up (out of order). Both cases were reproduced by mutating the code, and the race test fails both times. Duplicates are harmless; loss isn't. An `asyncio.Lock` belongs to the event loop it's first used on, and every test builds its own app. Cost: appends in one room are serialized, which they already were by SQLite's single writer. A slow client's catch-up holds up the room, as a slow client already holds up broadcast. Rejected: buffering live ops per connection during catch-up, which is more code for the same guarantee. |
| D-084: The server pushes catch-up on every connection, whether a first join, a late join or a reconnect, as ordinary `ops` messages plus `synced`. There's no `catch_up` request and no `snapshot` message type, and the protocol's TODO rows for them are gone. | One path for every case, so a client never has to know it's behind or ask. Ordinary `ops` go through `apply_message` unchanged (suppressed, LWW, tombstones), so the add-on needed no second apply path. Cost: a reconnect resends the whole state rather than only what's new. For a room of 200 objects that's about 200 messages and 107 KiB, which is fine now. A `join` carrying the last seen `seq` could send a delta later. |
| D-085: Merge on join. On the first `synced` of a Join, `detect.send_unknown_creates` sends a `create` for each local mesh whose ID the catch-up didn't mention (in a create, set or delete), skipping tombstoned IDs. A reconnect within the Join sends nothing extra. | Joining with a scene adds it to the room instead of silently hiding it from everyone else. "Mentioned in any op" counts objects from a shared `.blend` as known, so that workflow still works. Tombstoned IDs are skipped because Cmd+Z can bring back a deleted object with its old ID before the next flush retires it. On a reconnect, edits made meanwhile are already in the outbox. Not covered: edits made while not in a room, to objects the room knows, are never sent (documented in `addon/README.md`). |
| D-086: Catch-up `set`s and `delete`s are batched one origin per message, each at most `max_operation_bytes`; each `create` goes alone. | Protocol rule 4 says one origin per message, and the server's own `OpsMessage` rejects mixed ones, so a mixed batch would be a message the protocol forbids. Every catch-up message parses with `parse_message` in the tests. |
| D-087: `client.status()` keeps its four values; `client.synced()` is new, and the panel shows "Catching up with {room}…" until it's true. The reader tags each inbox entry with its socket's generation. | Changing what "connected" means would break the latency driver and a dozen tests. The generation tag stops a `synced` left in the inbox by a socket that died from marking the next socket as caught up. |

**Details:**
- Server: `app/sync/conflicts.py` (`RoomState`), `app/sync/state.py` (`load_state`,
  `maybe_snapshot`, `catch_up_messages`), the `Snapshot` model, `snapshot_every` in config (and
  compose / `.env.example`), catch-up and the lock in `app/realtime/websocket.py`, and REST in
  `app/api/snapshots.py`. Tests: `tests/sync/test_conflicts.py`, `tests/sync/test_state.py`,
  `tests/realtime/test_catch_up.py`, and `tests/catchup.py`, a connect helper that reads the
  catch-up first, which the existing relay tests now use.
- Add-on: `client.py` (`synced`, catch-up IDs, `on_synced`, generation tags), `detect.py`
  (`send_unknown_creates`, create records `Versions`), `apply.py` (create records `Versions`),
  `operators.py` (Join passes the hook), `panel.py` ("Catching up…"). Tests:
  `tests/test_catch_up.py` (a fake relay plays the server) and two create-as-write tests in
  `tests/test_create_delete.py`. One existing test changed: `test_apply_then_flush_sends_nothing`
  used a remote `set` at lamport 1, older than the cube's own `create`, which now loses.
- `scripts/smoke_client.py` (Docker smoke test, also in CI) reads the catch-up before checking
  the relay. `docker_smoke.sh` passes.
- **End to end, outside the test suites:** a throwaway script ran the real server and four
  headless Blender add-on processes, with `COLLAB_SNAPSHOT_EVERY=5`. All 11 checks passed: B
  joined empty and matched A; B left, A moved, deleted and created, B rejoined and matched, with
  its stale object removed; after a server restart, A reconnected by itself and a new client C
  matched; D joined with its own cube, kept it, and A and C got it; after another restart, D
  reconnected without resending anything; snapshots were written. No errors in any log. GUI
  Blender wasn't used: that's the manual check.
- Mutation-checked: no lock (join after reading, or join first) fails the race test; on_synced
  on every reconnect, no catch-up IDs, no generation check, no tombstone skip, and no
  create-as-write on either side each fail a test.
- The race test first hung in teardown about 1 run in 6: the client left while the server was
  still committing a backlog of thousands of appends, overlapping the app's shutdown. It now
  waits for the backlog (and is throttled).
- Latency, scenario 1 rerun with the lock: p50 56.8, p95 88.9, p99 100.8, max 105.3 ms (n=214),
  against 58.0 / 89.1 / 94.3 / 98.7 before; persist is 1.0 ms at p50, as before. A first attempt
  stalled after 58 nudges: both windows stopped drawing at the same moment, 18.6 s in, and A
  stopped producing edits while its other timers ran. A rerun was clean. It looks local to A's
  window rather than the server, but it isn't explained.

**Open / follow-up:**
- Log compaction: the log grows without limit. Snapshots make a join cheap regardless, but disk
  use keeps growing.
- A D-070 failed write still isn't repaired by catch-up: the sender has its edit locally and its
  `Versions` say it's newer, so the room's older value is skipped and that client stays different
  until someone edits the object again.
- Catch-up resends the full state on every reconnect (D-084). A `join` with the last seen `seq`
  could send only the tail.
- Merge on join with the default scene gives both clients two overlapping cubes (`Cube` and
  `Cube.001`, named the other way round on each side). That's by design, but it may surprise
  people in the demo.
- `apply_message` re-reads the whole scene per message, and catch-up sends each `create` alone,
  so joining a room of N objects is O(N²) in scene reads. Fine at the sizes tested; worth batching
  if rooms get large.
- #16 / #17: no auth on the socket or REST yet (TODO comments in place).

### 2026-11-09 · Fix: shutdown hang from cut-off queries (#20)

`tests/realtime/test_websocket.py` hung in teardown on this branch in about 1 test in 3 on
Lucas's machine (0 on main), and CI's server job ran for 20+ minutes before it was cancelled.
**Cause:** `_snapshot_if_due` opened a database session after every broadcast, inside the room
lock. A client that left right after a broadcast (or a test that ended, or shutdown) cancelled
the handler mid-query. The aiosqlite connection was left half-closed ("Exception terminating
connection" in the log, with a `CancelledError`), and `engine.dispose()` at shutdown then waited
for it forever. On this Mac the same error was logged in most runs but it never turned into a
hang, which is why my runs for #20 passed.

| Decision | Why |
|---|---|
| D-088: A connection handler never awaits the database itself. Queries (the append, catch-up's read) run through `AppTasks.shielded`, a task the app tracks and the handler awaits through `asyncio.shield`. Snapshots are no longer checked per message: `SnapshotScheduler` counts each room's appends in memory (seeded once from the database during the room's first catch-up in this process) and, when one is due, spawns one tracked task per room, outside the lock. The lifespan calls `AppTasks.shutdown()` before `engine.dispose()`: it sends close 1012 to every client, gives each handler 0.5 s to exit and then cancels it, then waits up to 5 s for the database work and cancels whatever overruns. | A handler can be cancelled at any await, by things outside our control, so the fix has to make that harmless rather than avoid it. A shielded query finishes and closes its session even if its caller is gone, and the shutdown order means nothing is using the engine when it's disposed. Counting in memory removes the per-message round trip, about 0.5 ms (D-082). A snapshot is only a cache, so skipping one is fine: a room that was never seeded counts from 0, a failed or cancelled snapshot is logged and skipped, and ops that arrive while one is being written count towards the next. Rejected: wrapping each query in `asyncio.shield` inline (the same idea, but nothing would track the orphaned task for shutdown), and catching `CancelledError` to close the session by hand (it's cancelled again by anyio's cancel scope, which is how it broke in the first place). |

**Details:**
- New: `server/app/realtime/tasks.py` (`AppTasks`). Changed: `SnapshotScheduler`,
  `ops_since_snapshot` and `write_snapshot` in `app/sync/state.py`, which replace
  `maybe_snapshot`; the handler in `app/realtime/websocket.py`; the lifespan in `app/main.py`,
  which now sets up the locks, tasks and scheduler (the `hasattr` lock hack is gone).
- **The regression guard:** the `client` fixture now records SQLAlchemy pool errors and fails
  the test if there are any, checked after shutdown. With the old code, 24 of the 33 relay tests
  fail it, and with the old per-message query put back into the new code, about 30 of 52 do.
  With the fix, none do.
- New tests: clients leaving right after a broadcast with a snapshot due every message (20
  rounds); a client leaving during a 301-message catch-up (10 times), after which the room still
  works; a snapshot at the threshold through the relay; real uvicorn with two clients connected
  and a snapshot due, stopped with SIGTERM (under 3 s, clean log); `AppTasks` unit tests
  (shielding, shutdown order, overrun); and scheduler tests (threshold, seeding, one per room,
  failure, cancellation mid-query).
- Hang-proofing: `pytest-timeout` in the server's dev deps, with `timeout = 30` per test, and
  `timeout-minutes: 10` on every CI job.
- Runs: `tests/realtime` 10 times (52 passed each) and the full server suite 3 times (622
  passed each), all under a watchdog, with no hang and no "terminating connection" in any output.
  Add-on: 144 passed. `docker_smoke.sh` passes. A separate Compose project with
  `COLLAB_SNAPSHOT_EVERY=1` and two connected clients that had just relayed: `docker compose stop`
  took 0.4 s, exit 0, and the clients got close code 1012. Uvicorn also sends 1012 to open
  connections on shutdown, before the lifespan's, so in Docker I can't tell which of the two
  closed them. Either way, `AppTasks.shutdown` waits for the snapshot tasks before the engine goes.

**Open / follow-up:**
- The hang never reproduced on this Mac, only the error that causes it. The pool-error check is
  what shows the fix, here and on CI.
- Snapshot tasks for one room don't queue: ops that arrive while one is running count towards
  the next, so with `COLLAB_SNAPSHOT_EVERY=1` some seqs are skipped. At 500 that's immaterial.

### 2026-11-09 · Accounts, rooms and per-room permissions (#16, #17, #18)

The success criterion is met: only an authenticated user who is a member of a room can join it,
and only an owner or editor can send operations. Accounts and tokens (#16), rooms, members and
invites over REST (#18), and roles enforced on the socket, in the REST API and on origins (#17).
That closes D-063. The add-on signs in from Preferences, and every script, test and the Docker
smoke test sign in too. One PR, three commits, one per issue.

| Decision | Why |
|---|---|
| D-089: Passwords are hashed with `hashlib.scrypt` (n=2^14, r=8, p=1, 32-byte key), with a 16-byte random salt per user, stored as `scrypt$n$r$p$salt$key` and compared with `hmac.compare_digest`. A login for an unknown user checks against a dummy hash. Usernames are 3–32 of `a-z0-9._-`, lowercased; passwords 8–256 characters. | scrypt is memory-hard and in the standard library, so no new dependency, as the issue asked. The parameters travel with each hash, so raising them later only affects new passwords. About 50 ms and 16 MiB per check, run in a thread so the relay isn't held up. The dummy hash makes a wrong username take as long as a wrong password, so neither the message nor the timing says which accounts exist. Lowercasing stops `Lucas` and `lucas` being two accounts that look the same. Rejected: bcrypt or argon2 (new dependencies, and nothing scrypt lacks here). |
| D-090: Login tokens are JWTs (PyJWT), HS256, signed with `COLLAB_SECRET_KEY`, with `sub` (user id), `iat` and `exp` (`COLLAB_TOKEN_TTL_HOURS`, default 168). `verify_token` checks the signature, the expiry and that the user still exists; the algorithm is pinned. There's no revocation list. The default-key warning is now a banner that says anyone can sign in as anyone, and a key under 32 bytes gets its own warning. | Stateless, so checking a token on every request is one signature check plus the user lookup. Pinning `algorithms` rules out `none` and algorithm confusion. A week keeps people signed in across a project without a refresh flow. Without revocation, signing out only forgets the token on that machine, so a leaked token is good until it expires; changing the key signs everyone out. Rejected: opaque tokens in a table (a lookup per request and a cleanup job, for revocation nobody needs yet). |
| D-091: The socket takes the token only from `Authorization: Bearer`; a query-string token is ignored. The server accepts, then closes before any catch-up with **4401** (no, bad or expired token) or **4403** (room missing, or not a member: one reason text for both). The add-on treats either as final: status `refused`, no reconnect, and the panel says "Sign in first" or "No access to <room>". | Uvicorn's access log records URLs, so a token there would end up in logs. Closing after accepting is the only way a client sees a code and a reason; a refused handshake is just a failed connect, which the add-on's backoff would retry forever. The same 4403 text for both cases doesn't tell anyone which rooms exist (REST still does: `POST /api/rooms` is `409` for a taken id, so that's not a secret, but the socket needn't add to it). Retrying with the same token can only fail the same way, so the backoff loop doesn't hammer the server. |
| D-092: A room is a record and must be created before anyone joins it; the creator is its owner. Its id stays the human-readable string the panel uses (`demo`). `rooms.created_by` is only a record: who may do what is in `room_members`, and a room always keeps at least one owner. | Without a record there's no one to ask "who is in this room". Readable ids keep the Blender panel working as it does. Keeping roles in one place means "owner" can't be true in two tables and false in one; several owners are allowed, so ownership can be handed over. A room's log is keyed by its id, so the first person to create `demo` on an existing database gets the operations `demo` had from before accounts. That's fine for dev data and is noted in `server/README.md`. |
| D-093: Invites: the owner gets a random 128-bit code once; only its SHA-256 is stored. Role `editor` or `viewer`, expiry 1–720 hours (24 by default). A code works for anyone who has it, any number of times, until it expires or is revoked (`404` unknown, `410` expired or revoked). Joining never lowers a role, and an existing member keeps the higher one. | A link to paste into a team chat is what the demo needs. Single-use codes would mean one per person, and the owner would have to know who's coming. The hash means a copy of the database can't be used to join. A fast hash is enough because the code is random, so there's nothing to guess. Expiry bounds how long a leaked link works, and revoking ends it early. Rejected: emailing invites (no email), and storing the code (it would work from a database backup). |
| D-094: An origin belongs to the first user who sends as it, recorded in `origin_owners` (origin → user, across all rooms). `OriginRegistry` checks the owner before its D-062 rules, so a takeover is only ever by the same user, and another user gets `origin … belongs to another user`. The registry is now one per app (`app.state.origins`). **Closes D-063.** | D-063 said only auth could tell a reconnect from a spoof, and now it can: the reconnect case is the same user. Keeping the owner in the database means a restart doesn't free an origin for whoever claims it first. It spans rooms because the add-on's origin does, and an origin seen in one room shouldn't be claimable in another. One registry per app because user ids only mean something within one database (tests run many apps in one process). The owner is looked up once per origin per process, through `tasks.shielded` (D-088). |
| D-095: Membership changes reach open sockets at once. Removing a member closes their sockets in that room with 4403 ("removed from room …"). A role change (or a higher role through an invite) updates the role on their open connections, from their next message, so a downgraded editor stays connected as a viewer. | Removal has to close the socket: a removed member must stop receiving the room too, not just stop sending. A downgrade only has to stop the edits, and staying connected means they keep seeing the room without having to rejoin. Both are in-process, which is all there is (one worker, as the Dockerfile says). The REST handler applies it after the commit, so a socket never has a role the database doesn't. |

**Details:**
- New: `app/auth/passwords.py`, `tokens.py`, `dependencies.py` (`Session`, `CurrentUser`),
  `membership.py` (`role_in`, `Member`), `permissions.py` (`Role`, `can_join`,
  `can_send_operations`, `can_manage`); `app/api/auth.py` and `rooms.py`; models `User`, `Room`,
  `RoomMember`, `Invite`, `OriginOwner`, and a `UTCDateTime` column type (SQLite drops the time
  zone, which made `expires_at` compare as naive). SQLite now enforces foreign keys.
- Changed: `app/realtime/websocket.py` (`_authorize`, `Access` on `websocket.state`, the viewer
  check before parsing, `_check_origin`, `member_changed`), `app/sync/validation.py`
  (`OriginRegistry` with owners), `app/api/snapshots.py` (members only), `app/main.py` (the
  louder warning, `app.state.origins`), `ConnectionManager.sockets`.
- Add-on: `account.py` (`login` with urllib, `http_url`), Sign in / Sign out in
  `preferences.py` (the password is a `SKIP_SAVE` operator property, cleared after use),
  `client.connect(..., token=)` sends the header, the reader uses `recv_data` so a close frame
  keeps its code, and a 4401 / 4403 close ends the writer with status `refused`. Join is
  enabled again when refused; `panel.status_text` says why.
- `server/scripts/admin.py`: `create-user`, `create-room --owner`, `add-member --role`, `token`,
  against the server's database (works with `docker compose exec`). Every socket script takes
  `--token` or `COLLAB_TOKEN`. `latency_run.py` registers a throwaway user, creates `--room` as
  them, passes the token to both Blenders and the load clients, and prints it for
  `latency_probe.py`. `docker_smoke.sh` registers and signs in with curl, creates the room,
  checks 4401 without a token and 4403 for a non-member (made with `admin.py`), and connects
  with a token.
- Tests: the `client` fixture is signed in as `tester` (`tests/accounts.py`), and
  `tests/catchup.py`'s `joined` creates the room if it doesn't exist, so the relay and catch-up
  tests run with every check on. `tests/auth/` covers tokens and scrypt, register / login / me,
  401 on every protected route, the rooms API (create, 409, list, details, invites: owner only,
  expired, revoked, reused, never lowering a role; roles; removal; the last owner), and the
  socket (4401 without or with a bad token, a query-string token ignored, 4403 for non-members
  and missing rooms, a viewer's catch-up and refused ops, an editor's ops, origins across users,
  a reconnect taking an origin back, ownership across a restart, removal closing with 4403,
  downgrade and upgrade on an open connection). `test_admin.py` runs `admin.py` as a process.
  Add-on: header sent, none without a token, no reconnect after 4401 / 4403, an ordinary close
  still reconnects, a fresh Join after a refusal, sign-in against a fake login server (token and
  name kept, password not), wrong password, unreachable server, sign-out, and the panel text.
- Mutation-checked: without the viewer check, without the origin owner check, and with
  `member_changed` doing nothing, each fails the tests that cover it (2, 7 and 4 tests).
- Runs: server suite 3 times, 732 passed each, no hangs; add-on 160 passed; `ruff` clean on
  both and on `scripts/`; `npm run build` passes; `docker_smoke.sh` passes (4401, 4403, relay
  with tokens, stop in 0 s with a client connected, restart and volume checks).

**Open / follow-up:**
- No rate limiting on login or register: scrypt makes each guess cost ~50 ms of server CPU,
  which also makes a flood of guesses a cheap way to load the server.
- No token revocation: Sign out only forgets the token locally, and a leaked token is good for
  up to a week. Changing `COLLAB_SECRET_KEY` signs everyone out.
- Open registration: anyone who can reach the server can make an account (though not join a
  room uninvited). A setting to turn it off would help on a shared network.
- Plain HTTP: passwords and tokens cross the network in the clear unless the server is behind
  HTTPS / `wss://`.
- A viewer's add-on still applies its own edits locally; the server refuses each with an error,
  so the viewer's scene drifts from the room until they rejoin, and dragging logs an error per
  flush. The add-on could learn its role and stop sending (it isn't told yet).
- The "last owner" check reads then writes, so two owners demoting each other at the same moment
  could both succeed. Unlikely with a handful of people; a transaction-level check would fix it.
- `auth_token` is saved in Blender's `userpref.blend` in plain text when preferences are saved.
- Presence (#22): who's in a room now; `Access` on each socket is the start of it.
- The web UI (`web/`) doesn't sign in yet.

### 2026-11-09 · Convergence tests (#21)

The success criterion holds, with one exception the tests found: after simultaneous edits, every
client ends with the same scene, which is also the room's state and what a late joiner gets. The
exception is two objects renamed to the same name at once (below). Tests only: no sync code
changed.

| Decision | Why |
|---|---|
| D-096: The convergence tests use their own reference client, `SimClient` (`server/tests/sync/sim.py`), written from protocol rules 1–3 and 9: a scene, a clock, versions per (object, property), tombstones and an outbox. It doesn't call `RoomState`, and `scene_of` reads the room's state off `to_ops()` directly. The fake relay gives each receiver a FIFO queue in `seq` order, because that's what the real relay does (it broadcasts under the room lock). | If the clients were simulated with `RoomState`, "the clients agree with the server" would be `RoomState` agreeing with itself. A second implementation from the spec makes the two check each other, and keeping it short (180 lines with its docstring) keeps it easy to check by eye. Per-receiver FIFO in `seq` order is what the real relay does: a looser order (a set overtaking its create) would only test a relay we don't have. |
| D-097: Conformance vectors live in one file at the repo root, `tests/vectors/convergence.json`, generated by `test_convergence.py` from 21 scripted scenarios. Each holds one observer's delivery stream and the scene it must end with. The server folds each with `RoomState`, and the add-on feeds each through the real `apply.apply_message` in headless Blender. The server test fails if the file is stale; `COLLAB_REGENERATE_VECTORS=1` rewrites it. A scenario the add-on is known to get wrong carries `known_divergence` and is a strict xfail on that side. | The model only matters if the real client matches it, and the add-on can't import server code (and vice versa), so a data file is the meeting point. Generated rather than written by hand, so the expected scenes come from the model, and checked for staleness so the two sides can't drift. `known_divergence` keeps a real disagreement visible in the file and in CI instead of leaving it out. |
| D-098: CI runs 300 fixed seeds (2–4 clients, 60 steps each) in about 0.5 s. `COLLAB_CONVERGENCE_SEEDS=N` runs N locally. A failure prints the seed and a trace shrunk by removing steps (halves, then singles) while it still fails. A separate test checks the generator still produces each conflict case often (ties, delete vs set, edits after a delete, rejoins). | Fixed seeds make CI reproducible, and a failure is replayable from the printed trace alone. The bias check stops a later change to the generator from quietly making conflicts rare, which would leave a green test that proves little. 20,000 seeds ran clean locally in 13 s. |

**What the tests found:**
- **A real divergence: the same name on two objects.** Blender keeps object names unique, so
  whichever object takes a name second becomes `Shared.001`. If client A renames X to "Shared"
  while B renames Y to "Shared", A applies Y's rename second and B applies X's second, so each
  ends with a different object called `Shared.001`. Nothing sends a correction, because
  `suppressed()` resyncs detect's cache after an apply. `RoomState` and the model both say "both
  are called Shared". It's recorded as vector `same_name_on_two_objects` (a strict xfail in the
  add-on) and as `test_two_clients_renaming_two_objects_to_one_name_converge` (strict xfail).
  **Not fixed: it's a sync-logic change, for Lucas to decide.** Options: names synced as
  "requested name" with each client showing Blender's suffix (compare only the base name), a
  deterministic suffix by (lamport, origin), or the add-on sending back the name Blender actually
  gave.
- **Everything else agreed.** 300 CI seeds and 20,000 local ones, with no divergence between
  clients, the room's state and a fresh joiner. 21 vectors: the real add-on matched the model
  on all 20 others. Mutations caught:
  - `RoomState`: origin order reversed (seed 27, shrunk to 6 steps); create-as-write removed (a
    vector); catch-up without deletes (4 tests).
  - The add-on: ties ignoring origin (5 vectors); a create not recorded as a write (2); a create
    ignoring tombstones (1).
  Two `RoomState` mutants weren't caught, and can't change a scene: `>=` instead of `>` for sets
  (op IDs are unique, so it never matters) and sets kept after a delete (`scene_of` has no
  object for them).
- **A harness bug, not a sync bug:** the first version of the relay test lost count when a
  message sent just before a reconnect was handled after the reconnecting peer's catch-up. It
  reached the peer live but uncounted, and the peer stopped one message short. Peers now quiesce
  before anyone disconnects or joins.
- **A small difference, harmless:** rule 1 says a client merges every timestamp it receives,
  and the model does. The add-on skips `clock.observe` for a `set` it drops (unknown or deleted
  object). Its clock can then be lower than the model's, but only by timestamps of ops that
  changed nothing, so last-writer-wins still orders every op that matters.

**Details:**
- `server/tests/sync/sim.py` (`SimClient`, `FakeRelay`, `scene_of`), `test_convergence.py`
  (scheduler, shrinker, bias check, vectors, limits), `tests/realtime/test_convergence_relay.py`
  (3 signed-in editors on real sockets, one away and back, a late fourth, against the REST
  snapshot; waits on message counts, no sleeps; 3 seeds, about 0.1 s each),
  `addon/tests/test_convergence_vectors.py`, and `tests/vectors/convergence.json`.
- The scheduler's steps: create (a small pool of IDs, never reused), set, a burst (2–4 clients
  edit one property before hearing each other: equal clocks, so ties broken by origin), delete,
  send (each create alone, then one batch, one set per key), deliver one message, drop (queued
  messages to it are lost, its outbox waits) and join (catch-up from the log's `RoomState`).
  Origins are ordered unlike the client index, so ties don't always go to client 0.
- Limits, as tests: D-070 is `test_a_failed_write_still_converges`, a strict xfail. Objects
  that were never created (pre-#15 shared `.blend`) are documented as they behave: clients that
  have the object apply its sets, and a late joiner without it gets nothing, because the log has
  no create to build it from. Viewers are left out: the relay refuses their ops (#17), so they
  can't affect anyone's scene.
- Runs: server 762 passed and 1 xfailed, 3 times, about 31 s each (the new tests add about
  1.5 s); add-on 181 passed and 2 xfailed (the new tests add about 0.6 s); ruff clean.
- Docs: `docs/protocol.md` has a "Known divergences" section; the test READMEs list the new
  files; `server/app/sync/README.md` marks the success criterion met.

**Open / follow-up:**
- Decide on same-name renames (above). Merge on join's `Cube` / `Cube.001` is the same cause,
  but there it's at least the same on both sides.
- The model doesn't cover merge on join (rule 10), rotation-mode details beyond what's stored,
  or collections. The vectors check the add-on's apply side only; detect's stamping and
  coalescing are covered by its own tests.

### 2026-11-09 · Web UI: sign-in, rooms, invites, who's connected (#22)

A React UI for everything the add-on can't do: register and sign in, list and create rooms,
invite people with a link, join by link, see who's connected from Blender, and (for owners)
change roles and remove members. It's served by the same server, so `docker compose up --build`
gives the UI and the API at http://localhost:8000. Small server additions: presence, and
serving the built app.

| Decision | Why |
|---|---|
| D-099: The image builds the UI in a Node stage and copies `web/dist` to `/srv/web` (`COLLAB_WEB_DIR`). FastAPI serves a file that exists there, and `index.html` for any other path, so client routes work on a reload. Paths under `/api/` and `/ws/` never fall back and stay JSON 404s, and `/health`, `/docs` and the routers come first anyway. Compose now builds from the repo root, with an allowlist in `server/Dockerfile.dockerignore`; the commented-out `web` service is gone. | Still one command and one port, as #23's success criterion wants. Same origin means no CORS and no second container, and the Blender "Server URL" is simply the page's own host. Node only exists in the build stage. The allowlist keeps a stray `.blend`, a venv or `node_modules` out of the build context. Rejected: a separate nginx container (a second service and a CORS setup, for no gain at this size). In dev, Vite proxies `/api` and `/ws` to :8000, so the app always calls its own origin. |
| D-100: `GET /api/rooms/{id}/presence` (members only) lists the users with an open socket in the room, once per user, with their current role and connection count. It reads `ConnectionManager` and each socket's `Access` (#17), and a removed member is left out at once. The room page polls it every 3 s while the tab is visible, and refreshes as soon as it becomes visible again. | It's what "see who is connected" needs, built from state the relay already has: no database, no new message type. Polling is a few small requests a minute per open page, and needs nothing new on the socket. Rejected: a presence WebSocket for browsers (a second socket protocol and its auth, to save a 3 s delay nobody notices). Like the rooms, it's one process's view, which is all there is (one worker). |
| D-101: The UI keeps its token in sessionStorage. Any 401 on a request that carried a token signs out, and the sign-in page shows at the same URL, so signing in again lands where you were. | sessionStorage survives a refresh but not closing the browser, and isn't shared between tabs, so two accounts in two tabs (the manual test) just work. Against localStorage: that would keep a week-long token on the disk until it expires, shared by every tab, so one sign-out signs out all of them and a second account needs a private window. Either is readable by script on the page, so XSS is the same risk both ways; an HttpOnly cookie would avoid that but needs CSRF protection and a server change, which is a follow-up if this is ever deployed beyond a trusted network. |
| D-102: No new runtime dependency. Routing is `useLocation` / `navigate` / `Link` over the History API (about 40 lines), and the look is plain CSS with light and dark from `prefers-color-scheme`. Test-only dev dependencies: vitest 4.1.12, @testing-library/react 16.3.3 and @testing-library/dom 10.4.2, and jsdom 29.1.1. | Four routes don't need react-router. jsdom 30 needs Node 22.22 or later, and this Mac has 22.14 (CI would be fine either way); 29.1.1 supports both. Versions are pinned exactly, and each is at least two weeks old. |

**Details:**
- **Pages:**
  - `SignInPage`: sign in or register, with the server's messages as they come, and validation
    errors as "field: message".
  - `RoomsPage`: my rooms with my role. Create checks the room-id rule as you type, and a 409
    becomes '"demo" is taken'.
  - `RoomPage`: connected now; Join from Blender (room id and server URL, each with a copy
    button, and "sign in to the add-on with this same account"); members; and for owners,
    invites (create, copy link, revoke) and role changes and two-step removal, which shows the
    server's "a room needs an owner…".
  - `JoinPage`: signed out, the sign-in form says you've been invited. Once signed in, it joins
    and replaces the URL with the room's.
- **API client** (`src/api/client.ts`): typed functions for every endpoint, and one place for
  the base URL, the Bearer header and error parsing. A network failure becomes "Can't reach the
  server", which the app shows with Try again instead of a blank page.
- **Server:** `presence()` in `app/realtime/websocket.py`, the route in `app/api/rooms.py`, and
  `app/web.py` (`add_web_routes`, called last in `create_app`, with a path check that stops
  `../` reaching outside the build). Tests: `tests/realtime/test_presence.py` (members only,
  connect and disconnect, two Blenders count 2, a role change shows at once, a refused socket
  never counts) and `tests/test_web.py` (`/`, built files, client routes, `/api` and `/ws` never
  falling back, traversal, API-only without a build, the socket beside the catch-all).
- **Web tests** (`src/test/app.test.tsx`, against a fake `fetch`): sign-in success and failure,
  register with a validation error, a 401 on load and mid-page signing out, Sign out, a taken
  room id, the room-id rule, create-then-go, invite create, copy and revoke, presence rendering
  and polling, the Blender box, the last-owner error, a role change, join by link signed out,
  an expired link, and the server down. Mutation-checked: without sign-out on 401, the two 401
  tests fail.
- **Tools:** the CI web job now runs `npm run lint` and `npm test` before the build.
  `docker_smoke.sh` checks that `/` serves the app, that `/join/anything` falls back to it, and
  that `/api/nope` is still a JSON 404.
- **npm:** npm 10.9.2 crashes ("reading 'edgesOut'") resolving vitest's optional jsdom peer.
  The one install was done with npm 11; `npm ci` with npm 10 installs from the lockfile fine.
- **Runs:**
  - Server: 782 passed and 1 xfailed, 3 times.
  - Add-on: 181 passed and 2 xfailed.
  - Web: lint clean, 17 tests pass, and the build passes.
  - `docker_smoke.sh`: all checks pass, the new UI ones included.
- **Not done:** I didn't click through the UI in a real browser; there's no browser here. The
  manual steps in the PR cover it.

**Open / follow-up:**
- The token is readable by any script on the page (D-101). An HttpOnly cookie would fix that,
  with CSRF protection to go with it.
- Invites made in an earlier visit aren't listed, because the server only shows a code once and
  has no list endpoint. Revoking an old one needs its code. A `GET …/invites` (without codes)
  could show what's outstanding.
- Presence shows connected users, not what they're doing (selection, viewport), which is out of
  scope. It's per process, as everything in the relay is.
- There's no leave-room button for non-owners yet (`DELETE …/members/<me>` exists).

