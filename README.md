# Collaborative
Collaborative is a backend-focused sync platform that lets several people edit the same project in a creative application at the same time, starting with Blender. Google Docs does this for text; complex creative tools have no equivalent, so collaborators pass files back and forth.

Each user runs Blender locally with an add-on. A FastAPI relay orders, validates and broadcasts small operations between them, so edits appear live. The server never runs Blender. Every user needs their own legal access to Blender.

See [docs/proposal.pdf](docs/proposal.pdf) for the full proposal, [docs/architecture.md](docs/architecture.md) for how the code maps to it, and [docs/devlog.md](docs/devlog.md) for the decisions made along the way.

## Repository layout

```
addon/                 Blender add-on (Python, runs inside Blender)
  collaborative_blender/
docs/                  Proposal, architecture notes, wire protocol
server/                FastAPI server (runs in Docker)
  app/
    api/               REST: accounts, rooms and invites, snapshots and history
    realtime/          WebSocket relay and room connections
    sync/              Sync engine: operations, Lamport clock, LWW, validation, log
    auth/              Tokens and per-room permissions
    db/                Models and sessions (SQLite now, Postgres later)
    storage/           Asset store interface + local-disk implementation
  tests/
    sync/              Sync engine tests
web/                   React + TypeScript UI (Vite): sign-in, rooms, connection status
docker-compose.yml     One command to run the server
```

## Running

### Run the server

You only need Docker. From the repo root:

```bash
docker compose up --build        # http://localhost:8000/health
```

Add `-d` to run it in the background. It then comes back by itself after a crash or a Docker
restart, until you `docker compose stop` or `down` it.

| To | Run |
|---|---|
| See a room's operation log | `docker compose exec server python scripts/show_log.py demo` |
| Stop, keeping the data | `docker compose down` |
| Reset all data | `docker compose down -v` |
| Check the whole setup | `scripts/docker_smoke.sh` (see below) |

**Connecting from Blender.** On the same machine, the add-on's default Server URL
(`ws://localhost:8000`) just works. From a second machine on your network, find the host's IP
(on a Mac, `ipconfig getifaddr en0`) and set the Server URL in the add-on's preferences to
`ws://<host-ip>:8000`. The host's firewall has to allow port 8000.

**Secret key.** `COLLAB_SECRET_KEY` defaults to `dev-only-change-me`, and the server logs a warning
at startup while it does. To set it, put `COLLAB_SECRET_KEY=...` in a `.env` file next to
`docker-compose.yml`; the other `COLLAB_*` settings in `server/.env.example` work the same way.
Nothing checks users yet (#16): anyone who can reach port 8000 can join any room, so only run this
on a network you trust.

**`unable to open database file`, restarting over and over?** The volume was created by an image
from before #23, which ran as root, and the server no longer does. `docker compose down -v`
fixes it, and deletes that data.

`scripts/docker_smoke.sh` builds from scratch and checks the relay, restarts, the volume and the
non-root user. It uses its own Compose project and volume, so your data is safe, but it needs port
8000 free.

### Other parts

**Server (local dev):**
```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
pytest
```

**Web UI:**
```bash
cd web
npm install
npm run dev                      # http://localhost:5173
```

**Blender add-on:** see [addon/README.md](addon/README.md).

## Status

| Milestone | Date |
|---|---|
| Blender change-detection spike | Oct 12 – 15 |
| Prototype: two-client transform sync | Oct 24 |
| Feature freeze | Nov 16 |
| Demo | Nov 23 |
