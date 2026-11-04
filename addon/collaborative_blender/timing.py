"""Out-of-band latency timing (#24): off unless COLLAB_TIMING names a JSONL file.

Operations can't carry timestamps (the schema forbids extra fields), so each side records when an
operation passed each stage, keyed by (origin, lamport, object), and scripts/latency_report.py
joins the files afterwards. `mark` only appends to a list, and a background thread writes the file,
so the measured path does no file I/O. Off, `now` and `mark` do nothing and no file is created.
"""

import atexit
import json
import os
import threading
import time
from collections import deque

FLUSH_INTERVAL = 1.0  # seconds

_path: str | None = None
_source = "?"
_buffer: deque[tuple] = deque()
_stop: threading.Event | None = None
_thread: threading.Thread | None = None


def enabled() -> bool:
    return _path is not None


def now() -> tuple[int, int] | None:
    """The current time on both clocks, or None when off, without reading either clock."""
    if _path is None:
        return None
    return time.perf_counter_ns(), time.time_ns()


def mark(stage: str, ops, at: tuple[int, int] | None = None) -> None:
    """Record that `ops` reached `stage`, now or `at` an earlier `now()`.

    `ops` is a list of operation dicts, or the raw JSON text of an `ops` message, which is only
    parsed later on the background thread so that a 64 KiB `create` costs nothing here.
    """
    if _path is None:
        return
    _buffer.append((stage, ops, at or now()))


def _keys(ops) -> list[dict]:
    if isinstance(ops, str):
        ops = json.loads(ops).get("ops", [])
    return [
        {"origin": op["origin"], "lamport": op["lamport"], "object": op["object"], "kind": op["kind"]}
        for op in ops
    ]


def flush() -> None:
    """Write everything recorded so far. Pops one at a time, since `mark` may run during this."""
    if _path is None or not _buffer:
        return
    with open(_path, "a", encoding="utf-8") as file:
        for _ in range(len(_buffer)):
            stage, ops, (mono_ns, wall_ns) = _buffer.popleft()
            try:
                keys = _keys(ops)
            except (ValueError, KeyError, TypeError, AttributeError):
                continue  # not an ops message, or a malformed one: nothing to key it by
            for key in keys:
                line = {"stage": stage, "source": _source, **key, "mono_ns": mono_ns}
                file.write(json.dumps({**line, "wall_ns": wall_ns}) + "\n")


def _run_flusher(stop: threading.Event) -> None:
    while not stop.wait(FLUSH_INTERVAL):
        flush()


def configure(path: str | None, source: str | None = None) -> None:
    """Turn timing on (writing to `path`) or off (None), flushing anything still buffered."""
    global _path, _source, _stop, _thread
    if _stop is not None:
        _stop.set()
        _thread.join(timeout=2)
        flush()
        _stop = _thread = None
    _path = path or None
    _source = source or os.environ.get("COLLAB_CLIENT", "?")
    if _path is not None:
        _stop = threading.Event()
        _thread = threading.Thread(target=_run_flusher, args=(_stop,), daemon=True)
        _thread.start()


atexit.register(flush)
configure(os.environ.get("COLLAB_TIMING"))
