"""Tests for AppTasks (#20): shielded database work and shutdown order."""

import asyncio
import time

from app.realtime import tasks as app_tasks
from app.realtime.tasks import AppTasks


class _FakeSocket:
    def __init__(self):
        self.closed_with = None

    async def close(self, code):
        self.closed_with = code


async def test_a_cancelled_caller_does_not_cut_shielded_work_off():
    tasks = AppTasks()
    finished = asyncio.Event()

    async def query():
        await asyncio.sleep(0.05)
        finished.set()
        return "rows"

    caller = asyncio.create_task(tasks.shielded(query()))
    await asyncio.sleep(0.01)
    caller.cancel()

    await asyncio.wait_for(finished.wait(), 1)
    assert caller.cancelled()
    await asyncio.sleep(0)
    assert tasks.busy == 0


async def test_shielded_returns_the_result_and_raises_the_error():
    tasks = AppTasks()

    async def ok():
        return 42

    async def broken():
        raise ValueError("no")

    assert await tasks.shielded(ok()) == 42
    try:
        await tasks.shielded(broken())
    except ValueError as exc:
        assert str(exc) == "no"
    else:
        raise AssertionError("the error was swallowed")


async def test_shutdown_closes_and_ends_handlers_then_waits_for_their_work():
    tasks = AppTasks()
    socket = _FakeSocket()
    work_done = asyncio.Event()

    async def handler():
        with tasks.handler(socket):
            await asyncio.sleep(3600)  # a client that never answers the close frame

    async def work():
        await asyncio.sleep(0.2)
        work_done.set()

    running = asyncio.create_task(handler())
    tasks.spawn(work())
    await asyncio.sleep(0.01)

    started = time.monotonic()
    await tasks.shutdown()

    assert time.monotonic() - started < 2
    assert socket.closed_with == 1012
    assert running.cancelled()
    assert work_done.is_set()  # waited for, not cancelled
    assert tasks.busy == 0


async def test_shutdown_cancels_work_that_overruns(monkeypatch):
    monkeypatch.setattr(app_tasks, "BACKGROUND_TIMEOUT", 0.1)
    tasks = AppTasks()
    stuck = tasks.spawn(asyncio.sleep(3600))

    started = time.monotonic()
    await tasks.shutdown()

    assert time.monotonic() - started < 1
    assert stuck.cancelled()


async def test_shutdown_with_nothing_running_returns_at_once():
    started = time.monotonic()
    await AppTasks().shutdown()
    assert time.monotonic() - started < 0.1
