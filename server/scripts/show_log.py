#!/usr/bin/env python3
"""Dev aid: print a room's operation log (#19), from the database the server uses.

Reads the same COLLAB_DATABASE_URL as the server, and its default path is relative, so run this
from server/ as you do the server. Safe while the server is running.

Usage (from server/, with the venv active):
    python3 scripts/show_log.py <room_id> [--after N]
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy.exc import OperationalError

# Running a script puts scripts/ on the import path, not server/, where `app` lives.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.db.models import Operation
from app.db.session import create_engine, create_session_factory
from app.sync import log


def _summary(row: Operation) -> str:
    """The part of an operation worth reading: what changed, without a whole mesh."""
    op = json.loads(row.payload)
    if row.kind == "set":
        return f"{op['property']} = {json.dumps(op['value'])}"
    if row.kind == "create":
        return (
            f"{op['name']!r} in {op['collection']!r}, {len(op['mesh']['vertices'])} vertices, "
            f"{len(op['mesh']['faces'])} faces"
        )
    return ""


async def _show(room_id: str, after_seq: int) -> int:
    engine = create_engine(settings.database_url)
    sessions = create_session_factory(engine)
    count = 0
    try:
        async with sessions() as session:
            while rows := await log.since(session, room_id, after_seq):
                for row in rows:
                    print(
                        f"{row.seq:>6}  {row.received_at:%Y-%m-%d %H:%M:%S} UTC"
                        f"  lamport={row.lamport:<6} origin={row.origin[:8]}"
                        f"  object={row.object[:8]}  {row.kind:<6} {_summary(row)}".rstrip()
                    )
                count += len(rows)
                after_seq = rows[-1].seq
    except OperationalError as exc:
        print(f"Can't read the log at {settings.database_url}: {exc.orig}", file=sys.stderr)
        print("Has the server run from this folder yet?", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    print(f"{count} operation(s) in room {room_id!r}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a room's operation log.")
    parser.add_argument("room_id")
    parser.add_argument("--after", type=int, default=0, metavar="N", help="only seq above N")
    args = parser.parse_args()
    return asyncio.run(_show(args.room_id, args.after))


if __name__ == "__main__":
    sys.exit(main())
