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
web/                   React + TypeScript UI (Vite): sign-in, rooms, invites, who's connected
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
| Make a user, a room, a token | `docker compose exec server python scripts/admin.py --help` |
| Stop, keeping the data | `docker compose down` |
| Reset all data | `docker compose down -v` |
| Check the whole setup | `scripts/docker_smoke.sh` (see below) |

**Connecting from Blender.** On the same machine, the add-on's default Server URL
(`ws://localhost:8000`) just works. From a second machine on your network, find the host's IP
(on a Mac, `ipconfig getifaddr en0`) and set the Server URL in the add-on's preferences to
`ws://<host-ip>:8000`. The host's firewall has to allow port 8000.

**Secret key.** `COLLAB_SECRET_KEY` signs login tokens. It defaults to `dev-only-change-me`, which
is in this repository, so anyone could forge a token for any user; the server prints a loud
warning at startup while it's in use. Set your own before anyone else can reach port 8000: put
`COLLAB_SECRET_KEY=...` (32+ characters, e.g. from
`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`) in a `.env` file next to
`docker-compose.yml`. The other `COLLAB_*` settings in `server/.env.example` work the same way.
Changing the key signs everyone out. Anyone who can reach the server can register an account, but
only a room's members can join it. Traffic is plain HTTP and `ws://`, passwords and tokens
included, so on anything but a network you trust, put it behind HTTPS.

**`unable to open database file`, restarting over and over?** The volume was created by an image
from before #23, which ran as root, and the server no longer does. `docker compose down -v`
fixes it, and deletes that data.

`scripts/docker_smoke.sh` builds from scratch and checks the relay, restarts, the volume and the
non-root user. It uses its own Compose project and volume, so your data is safe, but it needs port
8000 free.

### First run

Open **http://localhost:8000** after `docker compose up --build`. Accounts and rooms (#16–#18):
you sign in, a room has to exist before anyone joins it, and its owner invites everyone else.

1. **Register.** On the sign-in page, **Create an account** (3–32 letters, digits, `.`, `_` or
   `-`; a password of at least 8 characters).
2. **Create a room** under My rooms. You're its owner. Room ids are what people type into the
   Blender panel, so keep them short (`demo`).
3. **Invite someone.** On the room's page, under Invite someone, pick editor or viewer and how
   long the link lasts, then **Create invite link** and **Copy link**. The other person opens it,
   signs in or creates an account, and lands in the room. The code is shown only once; Revoke
   stops it working.
4. **Sign in from Blender.** The room page's "Join from Blender" box has the room id and the
   Server URL, each with a copy button. In Blender: Edit > Preferences > Add-ons > Collaborative,
   paste the Server URL, and **Sign in** with the same account as in the browser. The add-on
   keeps a token (valid for a week), not the password.
5. **Join** the room from the Collaborative panel. The room page's "Connected now" shows who's
   in, refreshed every few seconds. Without signing in, the panel says "Sign in first", and
   without access "No access to demo"; signing in or being invited, then Join, tries again.

Owners also change roles and remove members on the room page. Without the UI,
`docker compose exec server python scripts/admin.py --help` does the same from a terminal, and
the REST API is in [docs/protocol.md](docs/protocol.md#rest) (`/docs` lists every route).

### Other parts

**Server (local dev):**
```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
pytest
```

**Web UI (dev):** with the server running on :8000,
```bash
cd web
npm install
npm run dev                      # http://localhost:5173; /api and /ws are proxied to :8000
npm test && npm run lint
```
In Docker the image builds it and the server serves it at `/`, so this is only for working on it.

**Blender add-on:** see [addon/README.md](addon/README.md).

## Status

| Milestone | Date |
|---|---|
| Blender change-detection spike | Oct 12 – 15 |
| Prototype: two-client transform sync | Oct 24 |
| Feature freeze | Nov 16 |
| Demo | Nov 23 |
