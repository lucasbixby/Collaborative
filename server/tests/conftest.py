import logging
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.db.models import Operation
from app.main import create_app
from app.sync import log


@pytest.fixture
def database_url(tmp_path) -> str:
    """A throwaway SQLite file, so tests never touch `./data`."""
    return f"sqlite+aiosqlite:///{tmp_path}/test.db"


class _PoolErrors(logging.Handler):
    """Collects SQLAlchemy pool errors, such as "Exception terminating connection": the sign
    that a query was cut off and its connection left half-closed, which makes shutdown hang."""

    def __init__(self) -> None:
        super().__init__(logging.ERROR)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@pytest.fixture
def client(database_url) -> Iterator[TestClient]:
    # Entering the context manager (rather than a bare `TestClient(...)`) gives every
    # websocket_connect() call from this client the same BlockingPortal, i.e. the same
    # background thread and event loop. Without it, concurrent websocket connections
    # (#11) each get their own portal, and broadcasting between them can deadlock.
    errors = _PoolErrors()
    pool_logger = logging.getLogger("sqlalchemy.pool")
    pool_logger.addHandler(errors)
    try:
        with TestClient(create_app(database_url)) as test_client:
            yield test_client
    finally:
        pool_logger.removeHandler(errors)
    # Checked after shutdown, so a connection a handler left open is caught too (#20).
    assert errors.messages == [], errors.messages


@pytest.fixture
def read_log():
    """Reads a room's log through a running app, on that app's own event loop."""

    def read(test_client: TestClient, room_id: str, after_seq: int = 0) -> list[Operation]:
        async def _read() -> list[Operation]:
            async with test_client.app.state.sessions() as session:
                return await log.since(session, room_id, after_seq)

        return test_client.portal.call(_read)

    return read
