"""Shared fixtures for headless add-on tests.

Tests run against the `bpy` module from PyPI: real Blender, no window. The add-on is
loaded through Blender's own add-on loader (addon_utils), the same path a user's
Blender takes, rather than by importing it directly.
"""

import asyncio
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest
import websockets

ADDON_NAME = "collaborative_blender"
ADDON_SOURCE = Path(__file__).resolve().parents[1] / ADDON_NAME

# Blender reads BLENDER_USER_SCRIPTS once, when bpy is first imported, so this must run
# before `import bpy`. A throwaway scripts folder keeps tests away from your real
# Blender preferences and add-ons.
_user_scripts = Path(tempfile.mkdtemp(prefix="collab-blender-"))
(_user_scripts / "addons").mkdir()
(_user_scripts / "addons" / ADDON_NAME).symlink_to(ADDON_SOURCE, target_is_directory=True)
os.environ["BLENDER_USER_SCRIPTS"] = str(_user_scripts)

import bpy  # noqa: I001  (must be imported before addon_utils)
import addon_utils


@pytest.fixture
def scene():
    """A fresh, empty scene for each test. Clears objects and non-persistent handlers."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


@pytest.fixture
def addon(scene):
    """The add-on enabled as Blender would enable it, and disabled again afterwards."""
    # On failure Blender prints the traceback (shown in pytest's captured output) and
    # returns None.
    module = addon_utils.enable(ADDON_NAME, default_set=True)
    assert module is not None, "Blender failed to enable the add-on; see captured stderr"
    yield module
    addon_utils.disable(ADDON_NAME, default_set=True)
    # Drop the cached module so the next test gets a clean import.
    for name in [m for m in sys.modules if m == ADDON_NAME or m.startswith(ADDON_NAME + ".")]:
        del sys.modules[name]


@pytest.fixture
def depsgraph_log(scene):
    """Records what Blender's depsgraph_update_post handler reports.

    Changes made from a script only reach the depsgraph when it is evaluated, so call
    `log.flush()` after making a change. It evaluates the scene and returns the updates
    recorded since the previous flush as (name, id type, transform?, geometry?) tuples.
    """
    log = _DepsgraphLog()
    bpy.app.handlers.depsgraph_update_post.append(log.handler)
    yield log
    if log.handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(log.handler)


class _DepsgraphLog:
    def __init__(self):
        self.updates = []

    def handler(self, scene, depsgraph):
        for update in depsgraph.updates:
            self.updates.append(
                (
                    update.id.name,
                    type(update.id).__name__,
                    update.is_updated_transform,
                    update.is_updated_geometry,
                )
            )

    def flush(self):
        bpy.context.view_layer.update()
        recorded, self.updates = self.updates, []
        return recorded


def wait_until(predicate, timeout=2.0, interval=0.01) -> None:
    """Poll `predicate` until it's true, for asserting on client.py's background
    threads (#12) without a fixed sleep. Raises on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s")


class FakeRelay:
    """A minimal WebSocket server (#12's tests, and #13's): records what it receives,
    and lets a test push a message to the connected client, or stop (and later
    restart) the server, on demand. Not the real relay — #11 has its own tests for that.
    """

    def __init__(self) -> None:
        self.received: list[str] = []
        self.port: int | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: websockets.Server | None = None
        self._sockets: list = []
        self._thread: threading.Thread | None = None
        self._stopped = False

    def start(self, port: int = 0) -> None:
        ready = threading.Event()

        def _run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop

            async def _main() -> None:
                # A short close_timeout: otherwise stop() waits (by default) up to 10 s
                # for a close-handshake ack the test's client never sends.
                self._server = await websockets.serve(
                    self._handler, "localhost", port, close_timeout=0.2
                )
                self.port = next(iter(self._server.sockets)).getsockname()[1]
                ready.set()
                await self._server.wait_closed()

            loop.run_until_complete(_main())

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        ready.wait(timeout=5)

    async def _handler(self, websocket) -> None:
        self._sockets.append(websocket)
        try:
            async for message in websocket:
                self.received.append(message)
        finally:
            if websocket in self._sockets:
                self._sockets.remove(websocket)

    def send_to_client(self, text: str) -> None:
        for socket in list(self._sockets):
            asyncio.run_coroutine_threadsafe(socket.send(text), self._loop).result(timeout=5)

    def stop(self) -> None:
        """Idempotent: a test may stop the relay itself, so the fixture's own teardown
        must not fail when it calls this a second time."""
        if self._stopped:
            return
        self._stopped = True
        if self._server is not None:

            async def _close() -> None:
                self._server.close()
                await self._server.wait_closed()

            asyncio.run_coroutine_threadsafe(_close(), self._loop).result(timeout=5)
        if self._thread is not None:
            self._thread.join(timeout=5)


@pytest.fixture
def relay():
    server = FakeRelay()
    server.start()
    yield server
    server.stop()
