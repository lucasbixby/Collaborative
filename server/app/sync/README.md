# Sync engine (hand-written)

This package is the core of Collaborative and is written and tested by hand.
Claude Code can review it, but should not write it.

| File | Responsibility |
|---|---|
| `operations.py` | The operation format: object, property, new value, Lamport timestamp, origin ID. Serialization to and from JSON. |
| `clock.py` | Lamport clock: tick on local events, merge on receive, tie-break by origin ID. |
| `validation.py` | Check every incoming operation: schema, size limit, allowed properties, value types. Untrusted input. |
| `conflicts.py` | Last-writer-wins per (object, property) using Lamport order. CRDT-style merging later, if time allows. |
| `log.py` | Append-only operation log per room, catch-up queries (`since=<lamport>`), snapshot compaction. |

Tests live in `server/tests/sync/`. The convergence test (simulated concurrent
clients end in identical state) is a success criterion in the proposal.

The operation format is also documented in [`docs/protocol.md`](../../../docs/protocol.md),
since the Blender add-on has to speak it too.
