# Notes for Claude

Collaborative: real-time collaborative editing for Blender. See `README.md` and `docs/architecture.md`.

## Rules

- **Do not write implementation code in `server/app/sync/`**, or for any issue labelled
  `hand-written`. Lucas writes the sync engine himself (decision D-007).
  Reviewing it, explaining it, and pointing out bugs is fine.
- **Tests in `server/tests/sync/` may be written by Claude when Lucas asks** (D-027, amending
  D-007). They are written from `docs/protocol.md`; never write the code that makes them pass.
- **Keep `docs/devlog.md` up to date.** After each working step (a feature, spike, or change of
  plan), add a log entry: what was done, each decision with a D-number and a short "why",
  details, and follow-ups. Update the "Current status" table and the decision index too.
- Reference the GitHub issue in commit messages, and use `Closes #N` when a commit finishes it.

## Testing

- Add-on: `cd addon && .venv/bin/pytest` (headless Blender via `bpy`); see `addon/README.md`.
- Server: `cd server && pytest`.
- Web: `cd web && npm run build`.
