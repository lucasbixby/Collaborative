"""The app's own tasks: connection handlers and the database work they start (#20, D-088).

A connection handler can be cancelled at any await: a client that leaves, a test that ends, or
shutdown. If that await is inside a database query, the aiosqlite connection is left half-closed,
and `engine.dispose()` at shutdown then waits for it forever. So handlers never await the
database directly. `shielded` runs the query in a task of its own, which a cancelled handler
leaves to finish and close its session, and `spawn` does the same for work nobody waits for
(snapshots). `shutdown` ends handlers first, then waits for those tasks, so the engine is only
disposed once nothing is using it.
"""

import asyncio
import logging
from collections.abc import Coroutine, Iterator
from contextlib import contextmanager, suppress
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

HANDLER_CLOSE_TIMEOUT = 0.5  # seconds, at shutdown: to send a close frame, then to exit after it
BACKGROUND_TIMEOUT = 5.0  # seconds to let database work finish at shutdown before cancelling it


class AppTasks:
    def __init__(self) -> None:
        self._background: set[asyncio.Task] = set()
        self._handlers: dict[asyncio.Task, WebSocket] = {}

    def spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """Run `coro` as a task that shutdown waits for."""
        task = asyncio.get_running_loop().create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._finished)
        return task

    def _finished(self, task: asyncio.Task) -> None:
        self._background.discard(task)
        if not task.cancelled() and task.exception() is not None:
            # Whoever awaited it handled the error; this is for a caller that was cancelled.
            logger.debug("background task failed", exc_info=task.exception())

    async def shielded(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Await `coro` without letting a cancelled caller cut it off mid-query."""
        return await asyncio.shield(self.spawn(coro))

    @contextmanager
    def handler(self, websocket: WebSocket) -> Iterator[None]:
        """Register the current task as `websocket`'s handler for as long as the block runs."""
        task = asyncio.current_task()
        self._handlers[task] = websocket
        try:
            yield
        finally:
            self._handlers.pop(task, None)

    @property
    def busy(self) -> int:
        """How many handlers and background tasks are still running."""
        return len(self._handlers) + len(self._background)

    async def shutdown(self) -> None:
        """End every handler (close frame 1012, "service restart", then cancel), then let the
        database work they started finish, cancelling it only if it overruns. Afterwards
        nothing is using the engine, so it can be disposed."""
        handlers = list(self._handlers.items())
        for _task, websocket in handlers:
            with suppress(Exception):
                await asyncio.wait_for(websocket.close(code=1012), HANDLER_CLOSE_TIMEOUT)
        if handlers:
            # A client that answers the close frame ends its handler normally; cancel the rest.
            _done, still_running = await asyncio.wait(
                [task for task, _ in handlers], timeout=HANDLER_CLOSE_TIMEOUT
            )
            for task in still_running:
                task.cancel()
            await asyncio.gather(*still_running, return_exceptions=True)

        if self._background:
            _done, pending = await asyncio.wait(set(self._background), timeout=BACKGROUND_TIMEOUT)
            for task in pending:
                logger.warning("cancelling database work still running at shutdown")
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
