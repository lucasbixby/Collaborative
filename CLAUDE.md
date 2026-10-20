# Notes for Claude

Collaborative: real-time collaborative editing for Blender. See `README.md` and `docs/architecture.md`.

## Rules

- **Claude writes all code, including the sync engine** (D-028, replacing D-007 and D-027).
- **Explain every piece of code you write in 2–3 sentences** in your reply: what it does and
  why it's done that way. Lucas reads these to understand the code he's responsible for.
- **Keep `docs/devlog.md` up to date.** After each working step (a feature, spike, or change of
  plan), add a log entry: what was done, each decision with a D-number and a short "why",
  details, and follow-ups. Update the "Current status" table and the decision index too.
- Reference the GitHub issue in commit messages, and use `Closes #N` when a commit finishes it.

## How work is split

- **Two Claude sessions:** a planning chat (claude.ai) manages GitHub issues, the board,
  specs and reviews; Claude Code running in this folder implements. Issues on GitHub carry the
  current design and checklist: read the issue before starting work on it.
- Start each piece of work with `git pull`. When you finish, update the devlog yourself, then
  commit with `Closes #N` and push.

## Testing

- Add-on: `cd addon && .venv/bin/pytest` (headless Blender via `bpy`); see `addon/README.md`.
- Server: `cd server && pytest`.
- Web: `cd web && npm run build`.
