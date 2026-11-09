# Sync engine

The core of Collaborative: what an operation is, how operations are ordered, how
conflicts resolve, and what is accepted from clients.

| File | Responsibility |
|---|---|
| `operations.py` | The operation format from `docs/protocol.md` as Pydantic models; `parse_message` / `serialize_message`. **Done (#7).** |
| `clock.py` | Lamport clock: tick on local events, merge on receive, tie-break by origin ID. |
| `validation.py` | `OriginRegistry`: which connection may send as which `origin`. Schema and size checks are in `operations.py`. **Done (#10).** |
| `conflicts.py` | `RoomState`: folds a room's operations with the clients' rules (last-writer-wins per (object, property), deletes win, first create wins) into its current state, as ordinary ops. **Done (#20).** CRDT-style merging later, if time allows. |
| `log.py` | Append-only operation log per room; `since` reads it by `seq`, the catch-up cursor. **Done (#19).** Never trimmed; compaction is a follow-up. |
| `state.py` | A room's current state: `load_state` (latest snapshot + the log after it), `SnapshotScheduler` (counts appends in memory and writes a snapshot in a background task every `COLLAB_SNAPSHOT_EVERY` ops) and `catch_up_messages` (the state as size-limited `ops` messages). Used by the socket's catch-up and by REST. **Done (#20).** |

Tests live in `server/tests/sync/`. The convergence test (simulated concurrent
clients end in identical state) is a success criterion in the proposal.

The operation format is also documented in [`docs/protocol.md`](../../../docs/protocol.md),
since the Blender add-on has to speak it too.
