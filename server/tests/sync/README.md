# Sync engine tests

Tests for `app/sync/`, written from `docs/protocol.md`.

- `test_operations.py` — the operation format (#7): examples parse, round trip, rejections
- `test_validation.py` — origin pinning and takeover (#10)
- `test_log.py` — the operation log (#19): append, since, restart, concurrent writers
- `test_conflicts.py` — `RoomState` (#20): every fold rule, `to_ops` order, storage, and
  random sequences (snapshot + tail equals one fold; arrival order doesn't matter)
- `test_state.py` — snapshots and catch-up messages (#20): threshold, restart, size limit
- `sim.py` — the reference client (`SimClient`, written from the protocol rules, not from
  `RoomState`) and `FakeRelay` for the convergence tests (#21)
- `test_convergence.py` — convergence (#21): seeded random runs of 2–4 clients biased toward
  conflicts, a shrinker for failures, the known limits (D-070, never-created objects), and the
  conformance vectors in `tests/vectors/convergence.json`

Catch-up over the socket and the REST endpoints are in `tests/realtime/test_catch_up.py`, and
convergence through the real relay in `tests/realtime/test_convergence_relay.py`.

`COLLAB_CONVERGENCE_SEEDS=5000 pytest tests/sync/test_convergence.py` runs more seeds than CI's
300; `COLLAB_REGENERATE_VECTORS=1` rewrites the vectors after a deliberate change to the model.

Planned:

- `test_clock.py` — tick, merge, tie-breaking by origin ID
