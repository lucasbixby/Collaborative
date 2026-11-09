"""Tests for a room's state on disk (#20): load_state, snapshots, restart, catch-up messages."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db.models import Snapshot
from app.db.session import create_engine, create_session_factory, create_tables
from app.main import create_app
from app.sync import log
from app.sync import state as room_state
from app.sync.conflicts import RoomState
from app.sync.operations import parse_message
from tests.catchup import joined
from tests.sync.test_conflicts import A, B, X, Y, create, delete, move

ROOM = "room"


def _message(*ops):
    return parse_message(json.dumps({"v": 1, "type": "ops", "ops": list(ops)}))


@pytest.fixture
async def sessions(database_url):
    engine = create_engine(database_url)
    await create_tables(engine)
    yield create_session_factory(engine)
    await engine.dispose()


@pytest.fixture
async def session(sessions):
    async with sessions() as session:
        yield session


class _Spawner:
    """Stands in for AppTasks.spawn: runs each snapshot task and lets the test wait for it."""

    def __init__(self):
        self.tasks = []

    def __call__(self, coro):
        task = asyncio.get_running_loop().create_task(coro)
        self.tasks.append(task)
        return task

    async def wait(self):
        await asyncio.gather(*self.tasks)
        self.tasks.clear()


@pytest.fixture
def spawner():
    return _Spawner()


@pytest.fixture
def scheduler(sessions, spawner):
    return room_state.SnapshotScheduler(sessions, spawner)


@pytest.fixture
def append(session, scheduler, spawner):
    """Append as the relay does: log the ops, tell the scheduler, and wait for any snapshot.
    Returns how many snapshot tasks that append started."""

    async def _append(*ops):
        seqs = await log.append(session, ROOM, _message(*ops))
        scheduler.appended(ROOM, len(seqs))
        started = len(spawner.tasks)
        await spawner.wait()
        return started

    return _append


async def _snapshots(session):
    return list(await session.scalars(select(Snapshot).order_by(Snapshot.seq)))


async def test_an_empty_room_is_empty_at_seq_0(session):
    state, seq = await room_state.load_state(session, ROOM)

    assert (state.to_ops(), seq) == ([], 0)


async def test_load_state_folds_the_whole_log(session):
    await log.append(session, ROOM, _message(create(lamport=1)))
    await log.append(session, ROOM, _message(move(1.0, lamport=2), move(2.0, lamport=3)))

    state, seq = await room_state.load_state(session, ROOM)

    assert state.to_ops() == [create(lamport=1), move(2.0, lamport=3)]
    assert seq == (await log.since(session, ROOM))[-1].seq


async def test_load_state_pages_past_the_since_limit(session, monkeypatch):
    monkeypatch.setattr(log, "MAX_SINCE_LIMIT", 2)
    for lamport in range(1, 6):
        await log.append(session, ROOM, _message(move(float(lamport), lamport=lamport)))

    state, _seq = await room_state.load_state(session, ROOM)

    assert state.to_ops() == [move(5.0, lamport=5)]


async def test_no_snapshot_below_the_threshold(session, append, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_every", 3)

    assert await append(move(1.0, lamport=1), move(2.0, lamport=2)) == 0
    assert await _snapshots(session) == []


async def test_a_snapshot_is_written_at_the_threshold_and_counts_from_the_last(
    session, append, monkeypatch
):
    monkeypatch.setattr(settings, "snapshot_every", 3)

    await append(create(lamport=1), move(1.0, lamport=2))
    assert await append(move(2.0, lamport=3)) == 1  # 3 ops: due
    assert await append(move(3.0, lamport=4)) == 0  # 1 past the snapshot
    await append(move(4.0, lamport=5))
    assert await append(move(5.0, lamport=6)) == 1  # 3 past the snapshot: due

    first, second = await _snapshots(session)
    assert RoomState.from_json(first.state).to_ops() == [create(lamport=1), move(2.0, lamport=3)]
    assert RoomState.from_json(second.state).to_ops() == [create(lamport=1), move(5.0, lamport=6)]


async def test_the_count_is_seeded_from_the_log_after_the_latest_snapshot(
    session, sessions, spawner, monkeypatch
):
    monkeypatch.setattr(settings, "snapshot_every", 3)
    await log.append(session, ROOM, _message(move(1.0, lamport=1), move(2.0, lamport=2)))

    restarted = room_state.SnapshotScheduler(sessions, spawner)
    restarted.seed(ROOM, await room_state.ops_since_snapshot(session, ROOM))
    await log.append(session, ROOM, _message(move(3.0, lamport=3)))
    restarted.appended(ROOM, 1)
    await spawner.wait()

    assert len(await _snapshots(session)) == 1
    assert await room_state.ops_since_snapshot(session, ROOM) == 0


async def test_seed_does_not_overwrite_a_live_count(scheduler, spawner, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_every", 3)
    scheduler.appended(ROOM, 2)
    scheduler.seed(ROOM, 0)  # a later connection's catch-up

    scheduler.appended(ROOM, 1)

    assert len(spawner.tasks) == 1
    await spawner.wait()


async def test_one_snapshot_at_a_time_per_room(scheduler, spawner, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_every", 1)

    scheduler.appended(ROOM, 1)
    scheduler.appended(ROOM, 1)  # the first hasn't run yet
    scheduler.appended("other", 1)

    assert len(spawner.tasks) == 2
    await spawner.wait()
    scheduler.appended(ROOM, 1)  # finished, so the next one may start
    assert len(spawner.tasks) == 1
    await spawner.wait()


async def test_a_failed_snapshot_is_logged_and_skipped(scheduler, spawner, monkeypatch, caplog):
    monkeypatch.setattr(settings, "snapshot_every", 1)

    async def broken(session, room_id):
        raise RuntimeError("disk full")

    monkeypatch.setattr(room_state, "write_snapshot", broken)
    scheduler.appended(ROOM, 1)
    await spawner.wait()

    assert "snapshot failed room=room" in caplog.text
    scheduler.appended(ROOM, 1)  # not stuck "running"
    assert len(spawner.tasks) == 1
    await spawner.wait()


async def test_a_cancelled_snapshot_leaves_no_connection_open(
    sessions, scheduler, spawner, monkeypatch, caplog
):
    # Cancelled mid-query, with its session open: the cleanup must still close the connection,
    # or disposing the engine afterwards waits for it forever.
    monkeypatch.setattr(settings, "snapshot_every", 1)
    in_query = asyncio.Event()
    real_since = log.since

    async def slow_since(session, room_id, after_seq=0, limit=log.MAX_SINCE_LIMIT):
        rows = await real_since(session, room_id, after_seq, limit)
        in_query.set()
        await asyncio.sleep(30)
        return rows

    monkeypatch.setattr(log, "since", slow_since)
    scheduler.appended(ROOM, 1)
    await asyncio.wait_for(in_query.wait(), 5)
    spawner.tasks[0].cancel()
    await asyncio.gather(*spawner.tasks, return_exceptions=True)

    async with sessions() as session:  # the pool still hands out a working connection
        assert await room_state.ops_since_snapshot(session, ROOM) == 0
    assert "Exception terminating connection" not in caplog.text


async def test_state_is_the_latest_snapshot_plus_the_log_after_it(session, append, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_every", 2)
    await append(create(lamport=1), move(1.0, lamport=2))  # snapshot
    await append(delete(obj=Y, lamport=3, origin=B))  # tail

    # Prove the snapshot is used: corrupt the log rows it covers.
    snapshot = (await _snapshots(session))[-1]
    for row in await log.since(session, ROOM):
        if row.seq <= snapshot.seq:
            row.payload = json.dumps(delete(lamport=99))
    await session.commit()

    state, seq = await room_state.load_state(session, ROOM)

    assert state.to_ops() == [
        create(lamport=1),
        move(1.0, lamport=2),
        delete(obj=Y, lamport=3, origin=B),
    ]
    assert seq > snapshot.seq


async def test_snapshots_are_per_room(session, append, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_every", 1)
    await append(create())

    other, _ = await room_state.load_state(session, "other")

    assert other.to_ops() == []
    assert {s.room_id for s in await _snapshots(session)} == {ROOM}


async def test_the_log_is_never_trimmed(session, append, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_every", 1)
    for lamport in range(1, 4):
        await append(move(float(lamport), lamport=lamport))

    assert len(await log.since(session, ROOM)) == 3
    assert len(await _snapshots(session)) == 3


def test_state_and_snapshots_survive_a_restart(database_url, monkeypatch):
    # The success criterion: write through one app, then a fresh one on the same file
    # gives a new client the same state, with the snapshot in use.
    monkeypatch.setattr(settings, "snapshot_every", 2)
    with TestClient(create_app(database_url)) as first:
        with joined(first, ROOM) as a, joined(first, ROOM) as b:
            a.send_text(json.dumps({"v": 1, "type": "ops", "ops": [create(lamport=1)]}))
            b.receive_text()
            a.send_text(json.dumps({"v": 1, "type": "ops", "ops": [move(1.0, lamport=2)]}))
            b.receive_text()
            a.send_text(json.dumps({"v": 1, "type": "ops", "ops": [delete(obj=Y, lamport=3)]}))
            b.receive_text()
        with joined(first, ROOM) as before:
            expected = before.catch_up

    with TestClient(create_app(database_url)) as second:
        with joined(second, ROOM) as fresh:
            assert fresh.catch_up == expected

        async def _count():
            async with second.app.state.sessions() as session:
                return len(list(await session.scalars(select(Snapshot))))

        assert second.portal.call(_count) == 1

    ops = [op for message in expected for op in message["ops"]]
    assert ops == [create(lamport=1), move(1.0, lamport=2), delete(obj=Y, lamport=3)]


# -- catch_up_messages --------------------------------------------------------------------


def _ops_of(messages):
    return [op for text in messages for op in json.loads(text)["ops"]]


def test_catch_up_sends_each_create_alone_then_batches_per_origin():
    state = RoomState().apply_all(
        [
            create(obj=X, lamport=1, origin=A),
            create(obj=Y, lamport=2, origin=B),
            move(1.0, obj=X, lamport=3, origin=A),
            move(2.0, obj=Y, lamport=4, origin=B),
            move(3.0, obj=X, lamport=5, origin=B, prop="scale"),
            delete(obj="33333333-3333-4333-8333-333333333333", lamport=6, origin=A),
        ]
    )

    messages = [json.loads(text) for text in room_state.catch_up_messages(state)]

    assert [[op["kind"] for op in m["ops"]] for m in messages] == [
        ["create"],
        ["create"],
        ["set", "delete"],
        ["set", "set"],
    ]
    for message in messages:
        assert len({op["origin"] for op in message["ops"]}) == 1
    assert sorted(map(json.dumps, _ops_of(map(json.dumps, messages)))) == sorted(
        map(json.dumps, state.to_ops())
    )


def test_an_empty_state_sends_no_ops_messages():
    assert room_state.catch_up_messages(RoomState()) == []


def test_every_catch_up_message_fits_and_parses():
    big = create(obj=X, lamport=1)
    big["mesh"]["vertices"] = [[0.123456, 0.654321, 0.111111]] * 1500
    objects = [f"{n:08x}-0000-4000-8000-000000000000" for n in range(3000)]
    state = RoomState().apply_all(
        [
            big,
            *(
                move(float(n), obj=obj, lamport=n + 2, origin=A if n % 2 else B)
                for n, obj in enumerate(objects)
            ),
            *(delete(obj=obj, lamport=10_000 + n) for n, obj in enumerate(objects[:500])),
        ]
    )

    messages = room_state.catch_up_messages(state)

    assert len(messages) > 3  # the sets really were split
    for text in messages:
        assert len(text.encode("utf-8")) <= settings.max_operation_bytes
        parse_message(text)  # valid by the server's own rules: schema, one origin, size
    assert sorted(map(json.dumps, _ops_of(messages))) == sorted(map(json.dumps, state.to_ops()))


def test_batches_split_exactly_at_the_limit():
    state = RoomState().apply_all(
        move(float(n), lamport=n + 1, prop="location", obj=f"{n:08x}-0000-4000-8000-000000000000")
        for n in range(50)
    )
    one = room_state.catch_up_messages(state)
    size = len(one[0].encode("utf-8"))

    assert len(one) == 1
    assert len(room_state.catch_up_messages(state, max_bytes=size)) == 1
    assert len(room_state.catch_up_messages(state, max_bytes=size - 1)) == 2
