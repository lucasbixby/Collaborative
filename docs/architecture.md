# Architecture

Full reasoning is in [proposal.pdf](proposal.pdf). Summary of how the repo maps to it:

```
Blender + add-on (addon/)  ──WebSocket──┐
                                        ├── FastAPI server (server/, in Docker)
React web UI (web/)        ──REST───────┘      ├── realtime/  WebSocket relay, rooms
Blender + add-on (addon/)  ──WebSocket──┘      ├── sync/      sync engine
                                               ├── api/       REST: accounts, rooms, snapshots
                                               ├── auth/      tokens, room permissions
                                               ├── db/        users, rooms, op log, snapshots
                                               └── storage/   assets by content hash
```

The server never runs Blender. Only small operations travel between clients.

## Decisions

- **FastAPI over Cloudflare** — one server holds all sync state, which is easier to build, test and reason about.
- **Storage behind an interface** — `storage/base.py`; R2 or S3 can be added without touching the sync engine.
- **SQLite first** — Postgres only if time allows; switching is a `COLLAB_DATABASE_URL` change.
- **All code is written by Claude Code, with a short explanation of each piece** (D-028, which replaced the earlier hand-written sync engine rule D-007).
