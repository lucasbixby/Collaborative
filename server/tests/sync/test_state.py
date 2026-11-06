"""Tests for a room's state on disk (#20): load_state, snapshots, restart, catch-up messages."""

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
async def session(database_url):
    engine = create_engine(database_url)
    await create_tables(engine)
    async with create_session_factory(engine)() as session:
        yield session
    await engine.dispose()


async def _append(session, *ops):
    await log.append(session, ROOM, _message(*ops))
    return await room_state.maybe_snapshot(session, ROOM)


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


async def test_no_snapshot_below_the_threshold(session, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_every", 3)

    assert await _append(session, move(1.0, lamport=1), move(2.0, lamport=2)) is None
    assert await _snapshots(session) == []


async def test_a_snapshot_is_written_at_the_threshold_and_counts_from_the_last(
    session, monkeypatch
):
    monkeypatch.setattr(settings, "snapshot_every", 3)

    await _append(session, create(lamport=1), move(1.0, lamport=2))
    first = await _append(session, move(2.0, lamport=3))  # 3 ops: due
    assert await _append(session, move(3.0, lamport=4)) is None  # 1 past the snapshot
    await _append(session, move(4.0, lamport=5))
    second = await _append(session, move(5.0, lamport=6))  # 3 past the snapshot: due

    assert [s.seq for s in await _snapshots(session)] == [first.seq, second.seq]
    assert RoomState.from_json(first.state).to_ops() == [create(lamport=1), move(2.0, lamport=3)]
    assert RoomState.from_json(second.state).to_ops() == [create(lamport=1), move(5.0, lamport=6)]


async def test_state_is_the_latest_snapshot_plus_the_log_after_it(session, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_every", 2)
    await _append(session, create(lamport=1), move(1.0, lamport=2))  # snapshot
    await _append(session, delete(obj=Y, lamport=3, origin=B))  # tail

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


async def test_snapshots_are_per_room(session, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_every", 1)
    await _append(session, create())

    other, _ = await room_state.load_state(session, "other")

    assert other.to_ops() == []
    assert {s.room_id for s in await _snapshots(session)} == {ROOM}


async def test_the_log_is_never_trimmed(session, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_every", 1)
    for lamport in range(1, 4):
        await _append(session, move(float(lamport), lamport=lamport))

    assert len(await log.since(session, ROOM)) == 3


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
