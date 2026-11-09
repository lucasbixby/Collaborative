"""Async engine and session factory, built from a database URL.

Only factories: nothing connects at import. The app builds its engine at startup and keeps the
session factory on `app.state` (D-065); scripts/show_log.py builds its own.
"""

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.models import Base

BUSY_TIMEOUT_MS = 5000


def _configure_sqlite(connection, _record) -> None:
    """Let several clients write at once (D-066). The timeout comes first: switching to WAL
    needs a lock itself, so without it that switch could fail with "database is locked".
    SQLite also ignores foreign keys unless asked, per connection (#18)."""
    cursor = connection.cursor()
    cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_engine(database_url: str) -> AsyncEngine:
    engine = create_async_engine(database_url)
    if engine.dialect.name == "sqlite":
        event.listen(engine.sync_engine, "connect", _configure_sqlite)
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: rows from `since` stay readable after their session closes.
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_tables(engine: AsyncEngine) -> None:
    """Create the database's folder (SQLite won't) and any missing tables. `create_all` never
    alters an existing table; there's no migrations tool yet (D-067)."""
    url = engine.url
    if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
