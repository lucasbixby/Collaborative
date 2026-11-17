# Server

FastAPI relay and sync engine. Run it from this folder, because the default database path is
relative to where you start it:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --ws-max-size 1048576
pytest
```

## Where the data lives

Every relayed operation is saved in a SQLite file, by default `server/data/collaborative.db`
(`COLLAB_DATABASE_URL`, see `.env.example`). The folder and tables are created at startup, and
`data/` is git-ignored. With WAL on, you'll also see `-wal` and `-shm` files next to it: they're
part of the database, so copy or delete all three together.

There's no migrations tool. At startup, missing tables are created and nullable columns added
since the database was made are added to it; any other change to a table needs a fresh database.
Uploaded project files are in `data/assets/` by content hash, and the generated signing key in
`data/secret.key`.

In Docker, the database is in `/srv/data`, on the `server-data` volume from `docker-compose.yml`.
See "Run the server" in the [main README](../README.md).

## Accounts, rooms and roles

Everything but `/health`, register and login needs a token (`Authorization: Bearer <token>`),
from `POST /api/auth/login`, and the socket takes it in the same header. A room is created with
a password (`POST /api/rooms`); its creator is the host (role `owner`), and anyone signed in who
knows the name and password joins as an editor (`POST /api/rooms/join`). The host can make
someone a viewer, remove them, or delete the room. The full API and the close codes (4401,
4403) are in `docs/protocol.md`.

Passwords, for accounts and rooms, are hashed with the standard library's scrypt. Tokens are
JWTs valid for `COLLAB_TOKEN_TTL_HOURS` (168), signed with `COLLAB_SECRET_KEY`, or if that's
unset with a key the server generates once and keeps in `COLLAB_SECRET_KEY_FILE`. Failed
sign-ins and room joins are limited to `COLLAB_AUTH_ATTEMPTS` per `COLLAB_AUTH_WINDOW_SECONDS`
for each client and name.

`scripts/admin.py` works on the same database as the server, for setup, demos and tests:

```bash
python3 scripts/admin.py create-user alice                # asks for the password
python3 scripts/admin.py create-room demo --owner alice --room-password "open sesame"
python3 scripts/admin.py add-member demo bob --role viewer
python3 scripts/admin.py token alice                      # prints a token, e.g. for ws_probe
```

In Docker: `docker compose exec server python scripts/admin.py ...`.

## Project files and saving

`PUT /api/rooms/{id}/file` (host only) stores the request body as the room's `.blend`, and
`GET` returns it to any member. Content is kept by SHA-256 under `COLLAB_ASSET_DIR`, at most
`COLLAB_MAX_FILE_BYTES` (512 MiB), and must start like a `.blend`. Replacing or deleting a
room's file removes the old content unless another room still uses it.

A guest's save arrives on the socket as `save_request` and waits, in memory, for the host:
`GET /api/rooms` lists it for the room's owners, and `POST …/save-requests/{id}` answers it.
Approving sends `save` to the host's own Blender, so it's a `409` while the host has no Blender
in the room. A request nobody answers expires after ten minutes.

## The web UI

With `COLLAB_WEB_DIR` set to a built `web/dist`, the server also serves the UI at `/` for a
browser. The Docker image builds it and sets it to `/srv/web`. Unset, as in local dev, the
server is API-only and the UI runs on Vite's dev server (`cd web && npm run dev`). The desktop
app carries its own copy of the UI and only uses the API.

## Room state and snapshots

A client that connects is sent the room's current state first, so Blenders don't need to share a
file. The state is the latest snapshot plus the log after it. A snapshot is written once a room's
log has grown `COLLAB_SNAPSHOT_EVERY` operations (default 500) past the last one, into the
`snapshots` table next to `operations`, where only the newest two per room are kept. The log
itself is never trimmed. To look at a room:

```bash
H="Authorization: Bearer $(python3 scripts/admin.py token alice)"   # a member's token
curl -H "$H" localhost:8000/api/rooms/demo/snapshot              # current state, as ops
curl -H "$H" "localhost:8000/api/rooms/demo/operations?since=40" # log rows after seq 40
```

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

`scripts/ws_probe.py <room_id> --token <token>` talks to the relay by hand, without Blender. Run
it from this folder, including when the server is in Docker: it reads `docs/protocol.md`, which
isn't in the image. The token is a room member's (`scripts/admin.py token <user>`); `COLLAB_TOKEN`
works too, and so it does for `scripts/latency_probe.py` and `latency_load.py`.
