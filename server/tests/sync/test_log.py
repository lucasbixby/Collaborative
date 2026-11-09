"""Tests for the operation log (#19): append, since, durability, and the database setup."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text

from app.db.models import Operation
from app.db.session import BUSY_TIMEOUT_MS, create_engine, create_session_factory, create_tables
from app.main import create_app
from app.sync import log
from app.sync.operations import parse_message
from tests.catchup import joined

SERVER_DIR = Path(__file__).resolve().parents[2]
PROTOCOL_MD = SERVER_DIR.parent / "docs" / "protocol.md"
ROOM = "room"
OBJECT = "6c1f2a9e-3b4d-4e5f-8a7b-9c0d1e2f3a4b"
ORIGIN = "0b7e5d21-8f3c-4a6b-9d2e-1f4a5b6c7d8e"
OTHER_ROOM = "other-room"


def _example_messages() -> list[dict]:
    document = PROTOCOL_MD.read_text(encoding="utf-8")
    blocks = [json.loads(block) for block in re.findall(r"```json\n(.*?)```", document, re.DOTALL)]
    return [block for block in blocks if block.get("type") == "ops"]


def _message(*lamports: int):
    """A parsed message with one `delete` per Lamport value."""
    ops = [
        {"kind": "delete", "object": OBJECT, "lamport": lamport, "origin": ORIGIN}
        for lamport in lamports
    ]
    return parse_message(json.dumps({"v": 1, "type": "ops", "ops": ops}))


@pytest.fixture
async def engine(database_url):
    engine = create_engine(database_url)
    await create_tables(engine)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine):
    async with create_session_factory(engine)() as session:
        yield session


# -- append -------------------------------------------------------------------------------


async def test_append_returns_increasing_seqs_in_list_order(session):
    first = await log.append(session, ROOM, _message(5, 3, 9))
    second = await log.append(session, ROOM, _message(1))

    assert len(first) == 3
    assert first == sorted(first)
    assert second[0] > first[-1]
    rows = await log.since(session, ROOM)
    assert [row.seq for row in rows] == first + second
    assert [row.lamport for row in rows] == [5, 3, 9, 1]  # arrival order, not Lamport order


@pytest.mark.parametrize("example", _example_messages(), ids=["set", "create", "delete"])
async def test_append_stores_each_operation_as_its_validated_json(session, example):
    message = parse_message(json.dumps(example))

    await log.append(session, ROOM, message)

    rows = await log.since(session, ROOM)
    assert [json.loads(row.payload) for row in rows] == json.loads(message.model_dump_json())["ops"]
    for row, op in zip(rows, example["ops"], strict=True):
        assert (row.room_id, row.kind, row.object) == (ROOM, op["kind"], op["object"])
        assert (row.lamport, row.origin) == (op["lamport"], op["origin"])
        assert row.received_at is not None


async def test_append_works_after_a_read_on_the_same_session(session):
    await log.since(session, ROOM)  # leaves a transaction open

    assert len(await log.append(session, ROOM, _message(1))) == 1


async def test_append_is_all_or_nothing(session):
    def fail_on_second_row(_mapper, _connection, target):
        if target.lamport == 2:
            raise RuntimeError("disk full")

    event.listen(Operation, "before_insert", fail_on_second_row)
    try:
        with pytest.raises(RuntimeError, match="disk full"):
            await log.append(session, ROOM, _message(1, 2, 3))
    finally:
        event.remove(Operation, "before_insert", fail_on_second_row)

    assert await log.since(session, ROOM) == []
    assert len(await log.append(session, ROOM, _message(4))) == 1  # the session still works


async def test_largest_allowed_lamport_fits(session):
    await log.append(session, ROOM, _message(2**63 - 1))

    assert (await log.since(session, ROOM))[0].lamport == 2**63 - 1


async def test_a_seq_is_never_reused_after_the_newest_rows_are_deleted(session):
    # #20's compaction may delete rows, and a reused seq would break the catch-up cursor.
    [seq] = await log.append(session, ROOM, _message(1))
    async with session.begin():
        await session.execute(text("DELETE FROM operations"))

    assert (await log.append(session, ROOM, _message(2)))[0] > seq


# -- since --------------------------------------------------------------------------------


async def test_since_keeps_rooms_apart(session):
    await log.append(session, ROOM, _message(1))
    await log.append(session, OTHER_ROOM, _message(2))
    await log.append(session, ROOM, _message(3))

    assert [row.lamport for row in await log.since(session, ROOM)] == [1, 3]
    assert [row.lamport for row in await log.since(session, OTHER_ROOM)] == [2]
    assert await log.since(session, "empty-room") == []


async def test_since_after_seq_is_exclusive(session):
    seqs = await log.append(session, ROOM, _message(1, 2, 3))

    rows = await log.since(session, ROOM, after_seq=seqs[0])

    assert [row.seq for row in rows] == seqs[1:]
    assert await log.since(session, ROOM, after_seq=seqs[-1]) == []


async def test_since_limit_takes_the_oldest(session):
    seqs = await log.append(session, ROOM, _message(1, 2, 3, 4))

    rows = await log.since(session, ROOM, limit=2)

    assert [row.seq for row in rows] == seqs[:2]


async def test_since_pages_through_a_log_longer_than_the_limit(session):
    seqs = await log.append(session, ROOM, _message(*range(1, 6)))

    first = await log.since(session, ROOM, limit=2)
    second = await log.since(session, ROOM, after_seq=first[-1].seq, limit=2)
    third = await log.since(session, ROOM, after_seq=second[-1].seq, limit=2)

    assert [row.seq for row in first + second + third] == seqs


@pytest.mark.parametrize(("limit", "expected"), [(0, 0), (-1, 0), (10**9, log.MAX_SINCE_LIMIT)])
async def test_since_clamps_limit(session, monkeypatch, limit, expected):
    # A negative LIMIT means "no limit" to SQLite. Lowered so the test needn't write 1000 rows.
    if expected:
        monkeypatch.setattr(log, "MAX_SINCE_LIMIT", 2)
        expected = 2
    await log.append(session, ROOM, _message(1, 2, 3))

    assert len(await log.since(session, ROOM, limit=limit)) == expected


# -- Durability and setup -----------------------------------------------------------------


def _ws(client: TestClient):
    return joined(client, ROOM)


def test_history_survives_a_restart(database_url, read_log):
    # The success criterion: write through one app, then read it from a fresh one.
    message = _example_messages()[0]
    origin_b = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    with TestClient(create_app(database_url)) as first:
        with _ws(first) as a, _ws(first) as b:
            a.send_text(json.dumps(message))
            b.receive_text()
        before = read_log(first, ROOM)

    with TestClient(create_app(database_url)) as second:
        after = read_log(second, ROOM)
        with _ws(second) as a, _ws(second) as b:
            resumed = json.loads(json.dumps(message))
            for op in resumed["ops"]:
                op["origin"] = origin_b
            a.send_text(json.dumps(resumed))
            b.receive_text()
        resumed_rows = read_log(second, ROOM, after_seq=after[-1].seq)

    assert len(before) == 2
    assert [(row.seq, row.payload) for row in after] == [(row.seq, row.payload) for row in before]
    assert resumed_rows[0].seq > before[-1].seq  # new history continues; nothing is overwritten


def test_startup_creates_a_missing_folder(tmp_path):
    path = tmp_path / "not" / "yet" / "there.db"

    with TestClient(create_app(f"sqlite+aiosqlite:///{path}")):
        pass

    assert path.exists()


def test_importing_the_app_opens_no_database(tmp_path):
    # D-065: `app.main` builds an app at import, which must not create ./data.
    env = {**os.environ, "COLLAB_DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path}/nope/x.db"}
    subprocess.run([sys.executable, "-c", "import app.main"], check=True, env=env, cwd=SERVER_DIR)

    assert not (tmp_path / "nope").exists()


async def test_connections_use_wal_and_a_busy_timeout(engine):
    async with engine.connect() as connection:
        assert (await connection.scalar(text("PRAGMA journal_mode"))) == "wal"
        assert (await connection.scalar(text("PRAGMA busy_timeout"))) == BUSY_TIMEOUT_MS


# -- scripts/show_log.py ------------------------------------------------------------------


def _show_log(database_url: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/show_log.py", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=SERVER_DIR,
        env={**os.environ, "COLLAB_DATABASE_URL": database_url},
    )


async def test_show_log_lists_a_room_and_honours_after(session, database_url):
    examples = [parse_message(json.dumps(example)) for example in _example_messages()]
    seqs = [seq for message in examples for seq in await log.append(session, ROOM, message)]
    await log.append(session, OTHER_ROOM, _message(77))

    everything = _show_log(database_url, ROOM)
    later = _show_log(database_url, ROOM, "--after", str(seqs[-2]))

    assert everything.returncode == 0, everything.stderr
    assert f"{len(seqs)} operation(s) in room" in everything.stdout
    assert "location = [1.0, 2.0, 0.5]" in everything.stdout
    assert "'Cube' in 'Collection', 8 vertices, 6 faces" in everything.stdout
    assert "lamport=77" not in everything.stdout
    assert "1 operation(s) in room" in later.stdout
    assert "delete" in later.stdout


def test_show_log_explains_a_missing_database(tmp_path):
    result = _show_log(f"sqlite+aiosqlite:///{tmp_path}/missing/x.db", ROOM)

    assert result.returncode == 1
    assert "Can't read the log" in result.stderr
    assert "Traceback" not in result.stderr
