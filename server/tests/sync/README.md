# Sync engine tests

Tests for `app/sync/`, written from `docs/protocol.md`.

- `test_operations.py` — the operation format (#7): examples parse, round trip, rejections
- `test_validation.py` — origin pinning and takeover (#10)
- `test_log.py` — the operation log (#19): append, since, restart, concurrent writers

Planned:

- `test_clock.py` — tick, merge, tie-breaking by origin ID
- `test_conflicts.py` — last-writer-wins on the same property
- `test_convergence.py` — simulated concurrent clients end in identical scene state
