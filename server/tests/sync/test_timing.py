"""Tests for the out-of-band latency timing (#24), on the server's side."""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.sync import timing
from tests.catchup import joined

ORIGIN = "0b7e5d21-8f3c-4a6b-9d2e-1f4a5b6c7d8e"
OBJECT = "6c1f2a9e-3b4d-4e5f-8a7b-9c0d1e2f3a4b"


def _message(lamport: int = 1) -> dict:
    op = {
        "kind": "set",
        "object": OBJECT,
        "property": "location",
        "value": [1.0, 2.0, 3.0],
        "lamport": lamport,
        "origin": ORIGIN,
    }
    return {"v": 1, "type": "ops", "ops": [op]}


@pytest.fixture
def timing_file(tmp_path):
    path = tmp_path / "timing.jsonl"
    timing.configure(str(path))
    yield path
    timing.configure(None)


def test_off_by_default_writes_nothing_and_reads_no_clock(client, tmp_path, monkeypatch):
    timing.configure(None)
    monkeypatch.chdir(tmp_path)

    with joined(client, "demo") as ws:
        ws.send_text(json.dumps(_message()))
        ws.close()

    timing.flush()
    assert timing.now() is None
    assert len(timing._buffer) == 0
    assert list(tmp_path.glob("*.jsonl")) == []


def test_a_relayed_message_records_each_stage_in_order(database_url, timing_file):
    with (
        TestClient(create_app(database_url)) as client,
        joined(client, "demo") as sender,
        joined(client, "demo") as receiver,
    ):
        sender.send_text(json.dumps(_message(7)))
        receiver.receive_text()

    timing.flush()
    lines = [json.loads(line) for line in timing_file.read_text().splitlines()]
    assert all((line["origin"], line["lamport"], line["object"]) == (ORIGIN, 7, OBJECT) for line in lines)
    assert all(line["source"] == "server" and line["kind"] == "set" for line in lines)
    assert [line["stage"] for line in lines] == [
        "server_received",
        "server_parsed",
        "server_persisted",
        "server_broadcast",
    ]
    times = [line["mono_ns"] for line in lines]
    assert times == sorted(times)
    assert times[-1] > times[0]  # really read a clock


def test_a_rejected_message_records_nothing(client, timing_file):
    with joined(client, "demo") as ws:
        ws.send_text("not json")
        assert json.loads(ws.receive_text())["type"] == "error"

    timing.flush()
    assert not timing_file.exists()
