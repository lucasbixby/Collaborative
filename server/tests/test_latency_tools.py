"""Tests for the scripts/ latency tools (#24): the join, percentile and round-trip math."""

import importlib.util
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look the module up here
    spec.loader.exec_module(module)
    return module


report = _load("latency_report")
MS = 1_000_000
ALL_STAGES = [
    ("A", "noticed", 0),
    ("A", "flush_start", 30),
    ("A", "queued", 31),
    ("A", "dequeued", 41),
    ("A", "sent", 42),
    ("server", "server_received", 43),
    ("server", "server_parsed", 44),
    ("server", "server_persisted", 46),
    ("server", "server_broadcast", 47),
    ("B", "received", 47),
    ("B", "drained", 57),
    ("B", "applied", 58),
]


def _write(folder: Path, lines: list[dict]) -> None:
    by_source: dict[str, list[dict]] = {}
    for line in lines:
        by_source.setdefault(line["source"], []).append(line)
    for source, group in by_source.items():
        with (folder / f"{source}.jsonl").open("a") as file:
            file.writelines(json.dumps(line) + "\n" for line in group)


def _line(source, stage, ms, origin="a", lamport=1, obj="o", kind="set") -> dict:
    return {
        "stage": stage,
        "source": source,
        "origin": origin,
        "lamport": lamport,
        "object": obj,
        "kind": kind,
        "mono_ns": ms * MS,
    }


def _op_lines(lamport=1, offset=0, stages=ALL_STAGES, **kwargs) -> list[dict]:
    return [_line(s, stage, ms + offset, lamport=lamport, **kwargs) for s, stage, ms in stages]


@pytest.mark.parametrize(
    ("percent", "expected"), [(50, 50), (95, 95), (99, 99), (100, 100), (1, 1), (0.1, 1)]
)
def test_percentile_is_nearest_rank(percent, expected):
    assert report.percentile(list(range(100, 0, -1)), percent) == expected


def test_percentile_of_a_small_list_is_a_real_sample():
    assert report.percentile([10, 20, 30], 50) == 20
    assert report.percentile([10, 20, 30], 95) == 30
    assert report.percentile([7], 99) == 7


def test_percentile_of_nothing_raises():
    with pytest.raises(ValueError):
        report.percentile([], 50)


def test_join_gives_end_to_end_and_stages_that_add_up(tmp_path):
    _write(tmp_path, _op_lines())

    found, unapplied = report.samples(report.load(tmp_path))

    assert unapplied == 0
    assert [(s.sender, s.receiver) for s in found] == [("A", "B")]
    assert found[0].end_to_end_ns == 58 * MS
    durations = report.stage_durations(found)
    assert durations["detect wait (50 ms tick)"] == [30]
    assert durations["writer wait (20 ms poll)"] == [10]
    assert durations["server: persist"] == [2]
    assert durations["drain wait (20 ms tick)"] == [10]
    assert sum(values[0] for values in durations.values()) == 58


def test_ops_join_on_the_whole_key(tmp_path):
    _write(tmp_path, _op_lines(lamport=1) + _op_lines(lamport=2, offset=100, obj="p"))

    found, _ = report.samples(report.load(tmp_path))

    assert sorted(s.end_to_end_ns / MS for s in found) == [58, 58]
    assert {s.key for s in found} == {("a", 1, "o"), ("a", 2, "p")}


def test_an_op_nobody_applied_is_counted_not_sampled(tmp_path):
    _write(tmp_path, [line for line in _op_lines() if line["stage"] != "applied"])

    found, unapplied = report.samples(report.load(tmp_path))

    assert (found, unapplied) == ([], 1)


def test_ops_from_a_simulated_client_are_not_samples(tmp_path):
    _write(tmp_path, [line for line in _op_lines() if line["source"] != "A"])

    assert report.samples(report.load(tmp_path)) == ([], 0)


def test_a_repeated_stage_keeps_the_first_time(tmp_path):
    _write(tmp_path, _op_lines() + [_line("B", "applied", 500)])

    found, _ = report.samples(report.load(tmp_path))

    assert found[0].end_to_end_ns == 58 * MS


def test_kind_filter(tmp_path):
    _write(tmp_path, _op_lines(lamport=1) + _op_lines(lamport=2, kind="create"))

    found, _ = report.samples(report.load(tmp_path), kind="create")

    assert [s.key[1] for s in found] == [2]


def test_warmup_is_dropped_by_time(tmp_path):
    lines = [line for i in range(5) for line in _op_lines(lamport=i + 1, offset=i * 1000)]
    _write(tmp_path, lines)

    found, _ = report.samples(report.load(tmp_path))

    assert [s.key[1] for s in report.drop_warmup(found, 2.0)] == [3, 4, 5]


def test_draw_delay_is_to_the_next_draw_after_applied(tmp_path):
    _write(tmp_path, _op_lines())
    with (tmp_path / "B.jsonl").open("a") as file:
        for ms in (50, 61, 70):
            file.write(json.dumps({"stage": "draw", "source": "B", "mono_ns": ms * MS}) + "\n")
    timings = report.load(tmp_path)

    found, _ = report.samples(timings)

    assert report.draw_delays(found, timings) == [3]


def test_round_trip_pairs_a_nudge_with_its_reply_on_one_clock(tmp_path):
    _write(
        tmp_path,
        [
            _line("A", "noticed", 100, origin="a", lamport=5),
            _line("A", "applied", 160, origin="probe", lamport=6),
            _line("A", "noticed", 300, origin="a", lamport=7),
            _line("A", "applied", 390, origin="probe", lamport=8),
            # Same Lamport pattern on another object: not a reply.
            _line("A", "applied", 999, origin="probe", lamport=6, obj="other"),
            # The next Lamport time from the same origin: not a reply either.
            _line("A", "applied", 999, origin="a", lamport=6),
        ],
    )

    assert sorted(report.round_trips(report.load(tmp_path))) == [60, 90]


def test_report_runs_end_to_end_and_flags_skewed_clocks(tmp_path, capsys):
    skewed = [
        (s, stage, ms - 20 if s == "server" else ms) for s, stage, ms in ALL_STAGES
    ]
    _write(tmp_path, _op_lines(stages=skewed))

    assert report.main([str(tmp_path), "--warmup", "0", "--timeline", "1"]) == 0

    output = capsys.readouterr().out
    assert "| **end to end** | 1 | 58.0 |" in output
    assert "Warning" in output


def test_report_fails_cleanly_on_an_empty_folder(tmp_path, capsys):
    assert report.main([str(tmp_path)]) == 1
    assert "No .jsonl" in capsys.readouterr().err


def test_probe_replies_at_the_next_lamport_with_its_own_origin():
    probe = _load("latency_probe")
    move = {
        "kind": "set",
        "object": "o",
        "property": "location",
        "value": [1.0, 2.0, 3.0],
        "lamport": 4,
        "origin": "a",
    }
    create = {"kind": "create", "object": "p", "lamport": 3, "origin": "a"}

    reply = probe.reply_to({"v": 1, "type": "ops", "ops": [create, move]}, "me")

    assert reply["ops"] == [{**move, "lamport": 5, "origin": "me"}]
    assert probe.reply_to({"v": 1, "type": "ops", "ops": [create]}, "me") is None
    assert probe.reply_to({"v": 1, "type": "error", "message": "x"}, "me") is None


def _run_probe(*args: str) -> subprocess.CompletedProcess:
    """A fresh interpreter, because websockets 17 loads `websockets.exceptions` lazily."""
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "latency_probe.py"), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_probe_help_exits_cleanly():
    result = _run_probe("--help")

    assert result.returncode == 0
    assert "room_id" in result.stdout
    assert "Traceback" not in result.stderr


def test_probe_without_a_room_shows_argparses_message():
    result = _run_probe()

    assert result.returncode == 2
    assert "the following arguments are required: room_id" in result.stderr
    assert "Traceback" not in result.stderr


def test_probe_shows_the_real_error_when_the_connection_is_refused():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]  # free once closed, so nothing listens there

    result = _run_probe("latency", "--url", f"ws://127.0.0.1:{port}")

    assert result.returncode == 1
    assert f"Couldn't connect to ws://127.0.0.1:{port}/ws/rooms/latency" in result.stderr
    assert "Connect call failed" in result.stderr
    assert "Traceback" not in result.stderr
