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


@pytest.fixture
def client(database_url) -> Iterator[TestClient]:
    # Entering the context manager (rather than a bare `TestClient(...)`) gives every
    # websocket_connect() call from this client the same BlockingPortal, i.e. the same
    # background thread and event loop. Without it, concurrent websocket connections
    # (#11) each get their own portal, and broadcasting between them can deadlock.
    with TestClient(create_app(database_url)) as test_client:
        yield test_client


@pytest.fixture
def read_log():
    """Reads a room's log through a running app, on that app's own event loop."""

    def read(test_client: TestClient, room_id: str, after_seq: int = 0) -> list[Operation]:
        async def _read() -> list[Operation]:
            async with test_client.app.state.sessions() as session:
                return await log.since(session, room_id, after_seq)

        return test_client.portal.call(_read)

    return read
