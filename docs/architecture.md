# Architecture

Full reasoning is in [proposal.pdf](proposal.pdf); decisions and their dates are in [devlog.md](devlog.md).

```
 each person's computer                                  one shared server (Docker)
┌──────────────────────────────────────┐
│ Collaborative app (desktop/ + web/)  │──REST──────────┐   FastAPI (server/)
│   log in, host / join, dashboard,    │                ├──  api/       accounts, rooms, project files, history
│   upload / download the .blend,      │                │    auth/      passwords, tokens, roles, rate limits
│   launch Blender, approve saves      │                │    realtime/  WebSocket relay, save requests
│              │ starts, with the room │                │    sync/      operations, last-writer-wins, log, snapshots
│              ▼ in the environment    │                │    db/        users, rooms, members, op log, snapshots
│ Blender + add-on (addon/)            │──WebSocket─────┘    storage/   project files by content hash
│   detect edits → ops, apply ops      │
└──────────────────────────────────────┘
```

The server never runs Blender. Two things travel:

- **The project file**, once per launch. The host's app uploads the `.blend`; everyone else's app downloads it. So every Blender starts from the same scene, with everything a `.blend` holds.
- **Operations**, live. Small messages for what changes after that (object transforms, names, mesh objects created and deleted), ordered and merged by the sync engine. A client that connects or reconnects first receives the room's current state.

Saving belongs to the host: the host's Blender writes the host's file and uploads it. Anyone else's save becomes a request the host approves or denies in the app.

## Decisions

- **FastAPI over Cloudflare.** One server holds all sync state, which is easier to build, test and reason about.
- **Storage behind an interface.** `storage/base.py`; object storage can be added without touching anything else.
- **SQLite.** Postgres would be a `COLLAB_DATABASE_URL` change, plus a look at `seq` ordering.
- **A desktop app, not only a web page.** A page can't start Blender or read a file's location, and both are the core of the flow. The UI is still a web app, so the server can serve it to a browser too.
- **All code is written by Claude Code, with a short explanation of each piece** (D-028).
