# Sync engine tests

Tests for `app/sync/`, written from `docs/protocol.md`.

- `test_operations.py` — the operation format (#7): examples parse, round trip, rejections
- `test_validation.py` — origin pinning and takeover (#10)
- `test_log.py` — the operation log (#19): append, since, restart, concurrent writers
- `test_conflicts.py` — `RoomState` (#20): every fold rule, `to_ops` order, storage, and
  random sequences (snapshot + tail equals one fold; arrival order doesn't matter)
- `test_state.py` — snapshots and catch-up messages (#20): threshold, restart, size limit

Catch-up over the socket and the REST endpoints are in `tests/realtime/test_catch_up.py`.

Planned:

- `test_clock.py` — tick, merge, tie-breaking by origin ID
- `test_convergence.py` — simulated concurrent clients end in identical scene state
