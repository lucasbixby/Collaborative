# Collaborative
Collaborative lets several people edit the same Blender project at the same time. Google Docs does this for text; complex creative tools have no equivalent, so collaborators pass files back and forth.

Each person runs Blender on their own computer. One of them hosts a room from a `.blend` file, the others join it with the room's name and password, and everyone's edits appear live in everyone's Blender. A FastAPI server orders, validates and relays small operations between them; it never runs Blender. Every user needs their own copy of Blender.

See [docs/proposal.pdf](docs/proposal.pdf) for the proposal, [docs/architecture.md](docs/architecture.md) for how the parts fit, [docs/protocol.md](docs/protocol.md) for the wire format and REST API, and [docs/devlog.md](docs/devlog.md) for the decisions made along the way.

## Using it

**Host**

1. Open the Collaborative app and log in, or create an account.
2. **Host room**: choose the `.blend` file the room starts from, give the room a name and a password, **Create room**.
3. The dashboard shows the rooms you host and the ones you've joined, each with who is in it right now.
4. Click a room, then **Launch Blender**. Blender opens your file, already in the room. Saving in Blender saves your file as usual and shares it with the room.
5. When someone else saves, the app asks you: "*name* would like to save the project". **Approve** saves your file from your Blender; **Deny** does nothing.

**Everyone else**

1. Open the app and log in, or create an account.
2. **Join room**: type the room's name and password.
3. Click the room, then **Launch Blender**. The app downloads the host's file and opens it in Blender, in the room.

## Repository layout

```
desktop/               The Collaborative app (Electron): the UI in a window, plus launching Blender
web/                   The UI itself (React + TypeScript, Vite)
addon/                 Blender add-on (Python, runs inside Blender; the app loads it)
server/                FastAPI server (runs in Docker)
  app/
    api/               REST: accounts, rooms, project files, history
    realtime/          WebSocket relay, save requests
    sync/              Sync engine: operations, last-writer-wins, validation, log, snapshots
    auth/              Passwords, tokens, roles, rate limits
    db/                Models and sessions (SQLite)
    storage/           Project files by content hash
docs/                  Proposal, architecture, wire protocol, devlog
docker-compose.yml     One command to run the server
```

## Running

### 1. The server (one, shared by everyone)

You only need Docker. From the repo root:

```bash
docker compose up --build        # http://localhost:8000/health
```

Add `-d` to run it in the background; it then comes back by itself after a crash or a Docker restart, until you `docker compose stop` or `down` it.

| To | Run |
|---|---|
| See a room's operation log | `docker compose exec server python scripts/show_log.py <room>` |
| Make a user, a room, a token by hand | `docker compose exec server python scripts/admin.py --help` |
| Stop, keeping the data | `docker compose down` |
| Reset all data | `docker compose down -v` |
| Check the whole setup | `scripts/docker_smoke.sh` |

People on other computers reach it at `http://<this computer's address>:8000` (on a Mac, `ipconfig getifaddr en0` prints the address). The firewall has to allow port 8000.

**Security, in short.** The server makes its own signing key on first start and keeps it in its data volume; set `COLLAB_SECRET_KEY` only if you want to choose it. Anyone who can reach the server can register an account, but only someone with a room's name and password can join it, and repeated wrong guesses are cut off. Traffic is plain HTTP and `ws://`, passwords included, so on any network you don't trust, put the server behind HTTPS. A project file is another person's `.blend`: the app opens files you didn't host with their embedded Python scripts switched off, but only join rooms of people you'd accept a file from.

### 2. The app (on each person's computer)

Needs Node 22 and Blender 5.2.

```bash
cd web && npm install && cd ../desktop && npm install
npm start                        # builds the UI and opens the app
```

In **Settings**, set the server address (the default is `http://localhost:8000`, right for the computer running the server) and, if Blender isn't in its usual place, where it is. Nothing has to be installed in Blender: the app starts it with the add-on.

The same UI is served by the server at `http://localhost:8000` for a browser, where you can manage accounts and rooms but not launch Blender.

### Working on it

| Part | Commands |
|---|---|
| Server | `cd server && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`, then `uvicorn app.main:app --reload --ws-max-size 1048576` and `pytest` |
| UI | `cd web && npm run dev` (http://localhost:5173, proxied to the server on :8000), `npm test`, `npm run lint` |
| App | `cd desktop && npm test` |
| Add-on | see [addon/README.md](addon/README.md) |

## Status

| Milestone | Date |
|---|---|
| Blender change-detection spike | Oct 12 – 15 |
| Prototype: two-client transform sync | Oct 24 |
| Feature freeze | Nov 16 |
| Demo | Nov 23 |
