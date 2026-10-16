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
    sync/              Sync engine: operations, Lamport clock, LWW, validation, log  (hand-written)
    auth/              Tokens and per-room permissions
    db/                Models and sessions (SQLite now, Postgres later)
    storage/           Asset store interface + local-disk implementation
  tests/
    sync/              Sync engine tests (hand-written)
web/                   React + TypeScript UI (Vite): sign-in, rooms, connection status
docker-compose.yml     One command to run the server
```

## Running

**Server (Docker):**
```bash
docker compose up --build        # http://localhost:8000/health
```

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
