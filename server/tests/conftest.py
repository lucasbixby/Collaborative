from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    # Entering the context manager (rather than a bare `TestClient(...)`) gives every
    # websocket_connect() call from this client the same BlockingPortal, i.e. the same
    # background thread and event loop. Without it, concurrent websocket connections
    # (#11) each get their own portal, and broadcasting between them can deadlock.
    with TestClient(create_app()) as test_client:
        yield test_client
