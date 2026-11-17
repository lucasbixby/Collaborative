"""Async engine and session factory, built from a database URL. Nothing connects at import:
the app builds its engine at startup and keeps the session factory on `app.state`."""

from pathlib import Path

from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.models import Base

BUSY_TIMEOUT_MS = 5000


def _configure_sqlite(connection, _record) -> None:
    """The timeout comes first: switching to WAL needs a lock itself. SQLite also ignores
    foreign keys unless asked, per connection."""
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
    # expire_on_commit=False: rows stay readable after their session closes.
    return async_sessionmaker(engine, expire_on_commit=False)


def _add_missing_columns(connection) -> None:
    """`create_all` never alters a table, so a nullable column added to a model since the
    database was made is added here. Anything else still needs a fresh database."""
    inspector = inspect(connection)
    for table in Base.metadata.sorted_tables:
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name not in existing and column.nullable:
                column_type = column.type.compile(connection.dialect)
                connection.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}')
                )


async def create_tables(engine: AsyncEngine) -> None:
    """Create the database's folder (SQLite won't), any missing tables, and missing columns."""
    url = engine.url
    if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(_add_missing_columns)
