# Sync engine tests

Hand-written alongside `app/sync/`. Planned files:

- `test_clock.py` — tick, merge, tie-breaking by origin ID
- `test_validation.py` — malformed, oversized, and disallowed operations are rejected
- `test_conflicts.py` — last-writer-wins on the same property
- `test_convergence.py` — simulated concurrent clients end in identical scene state
- `test_log.py` — append, catch-up since a timestamp, snapshot + replay
