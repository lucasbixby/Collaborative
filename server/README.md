# Server

FastAPI relay and sync engine. Run it from this folder, because the default database path is
relative to where you start it:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
pytest
```

After pulling #19, re-run the `pip install` line: async SQLAlchemy needs `greenlet`, which is a
new dependency.

## Where the data lives

Every relayed operation is saved in a SQLite file, by default `server/data/collaborative.db`
(`COLLAB_DATABASE_URL`, see `.env.example`). The folder and tables are created at startup, and
`data/` is git-ignored. With WAL on, you'll also see `-wal` and `-shm` files next to it: they're
part of the database, so copy or delete all three together.

There's no migrations tool yet (D-067). `create_all` adds missing tables but never changes an
existing one, so after a change to a table's columns, delete the file and start again.

In Docker, the database is in `/srv/data`, on the `server-data` volume from `docker-compose.yml`.
See "Run the server" in the [main README](../README.md).

## Room state and snapshots (#20)

A client that connects is sent the room's current state first, so Blenders don't need to share a
file. The state is the latest snapshot plus the log after it. A snapshot is written once a room's
log has grown `COLLAB_SNAPSHOT_EVERY` operations (default 500) past the last one, into the
`snapshots` table next to `operations`. The log itself is never trimmed. To look at a room:

```bash
curl localhost:8000/api/rooms/demo/snapshot              # current state, as ops
curl "localhost:8000/api/rooms/demo/operations?since=40" # log rows after seq 40
```

After pulling #20, an existing database just gains the `snapshots` table at startup (D-067).

## Reading the log

```bash
python3 scripts/show_log.py demo            # everything in room "demo"
python3 scripts/show_log.py demo --after 40 # only seq above 40
```

It reads the same `COLLAB_DATABASE_URL` as the server, so run it from this folder too. It's safe
while the server is running.

In Docker: `docker compose exec server python scripts/show_log.py demo`.

## Other dev aids

`COLLAB_TIMING=<file>` records latency timings; see `docs/latency.md`.

`scripts/ws_probe.py <room_id>` talks to the relay by hand, without Blender. Run it from this
folder, including when the server is in Docker: it reads `docs/protocol.md`, which isn't in the image.
