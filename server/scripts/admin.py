#!/usr/bin/env python3
"""Admin commands against the server's own database (#16-#18), for setup, demos and tests.

Reads the same COLLAB_DATABASE_URL and COLLAB_SECRET_KEY as the server, so run it from server/
as you do the server, or in the container. Safe while the server is running.

    python3 scripts/admin.py create-user <name> [--password P]   (else COLLAB_PASSWORD, else asks)
    python3 scripts/admin.py token <name>                        prints a login token
    docker compose exec server python scripts/admin.py token <name>
"""

import argparse
import asyncio
import getpass
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

# Running a script puts scripts/ on the import path, not server/, where `app` lives.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.auth import USERNAME_PATTERN
from app.auth import passwords
from app.auth.tokens import create_token
from app.config import settings
from app.db.models import User
from app.db.session import create_engine, create_session_factory, create_tables


class AdminError(Exception):
    """A command that can't be done, with a message for the person running it."""


async def _user(session, username: str) -> User:
    user = await session.scalar(select(User).where(User.username == username.lower()))
    if user is None:
        raise AdminError(f"no user {username!r}")
    return user


async def create_user(session, username: str, password: str) -> User:
    if not re.match(USERNAME_PATTERN, username.lower()):
        raise AdminError("a username is 3-32 letters, digits, '.', '_' or '-'")
    if len(password) < passwords.MIN_LENGTH:
        raise AdminError(f"the password needs at least {passwords.MIN_LENGTH} characters")
    user = User(
        username=username.lower(),
        password_hash=passwords.hash_password(password),
        created_at=datetime.now(UTC),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        raise AdminError(f"user {username!r} already exists") from None
    return user


async def token(session, username: str) -> str:
    return create_token((await _user(session, username)).id)


def _password(args) -> str:
    if args.password is not None:
        return args.password
    if os.environ.get("COLLAB_PASSWORD"):
        return os.environ["COLLAB_PASSWORD"]
    return getpass.getpass(f"Password for {args.username}: ")


async def _run(args) -> str:
    engine = create_engine(settings.database_url)
    await create_tables(engine)
    try:
        async with create_session_factory(engine)() as session:
            if args.command == "create-user":
                user = await create_user(session, args.username, _password(args))
                return f"created user {user.username!r}"
            if args.command == "token":
                return await token(session, args.username)
            raise AssertionError(args.command)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Admin commands for the Collaborative server.")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user", help="add an account")
    create.add_argument("username")
    create.add_argument("--password", help="else COLLAB_PASSWORD, else asked for")
    commands.add_parser("token", help="print a login token for a user").add_argument("username")
    args = parser.parse_args(argv)
    try:
        print(asyncio.run(_run(args)))
    except AdminError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
