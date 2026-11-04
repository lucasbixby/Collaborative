"""Out-of-band latency timing (#24): off unless COLLAB_TIMING names a JSONL file.

The server's half of addon/collaborative_blender/timing.py; see that file for the design. Records
when an operation passed each stage, keyed by (origin, lamport, object), for
scripts/latency_report.py to join. Off, `now` and `mark` do nothing and no file is created.
"""

import atexit
import json
import os
import threading
import time
from collections import deque

from app.sync.operations import OpsMessage

FLUSH_INTERVAL = 1.0  # seconds

_path: str | None = None
_buffer: deque[tuple] = deque()
_stop: threading.Event | None = None
_thread: threading.Thread | None = None


def now() -> tuple[int, int] | None:
    """The current time on both clocks, or None when off, without reading either clock."""
    if _path is None:
        return None
    return time.perf_counter_ns(), time.time_ns()


def mark(stage: str, message: OpsMessage, at: tuple[int, int] | None = None) -> None:
    """Record that `message` reached `stage`, now or `at` an earlier `now()`."""
    if _path is None:
        return
    _buffer.append((stage, message, at or now()))


def flush() -> None:
    """Write everything recorded so far. Pops one at a time, since `mark` may run during this."""
    if _path is None or not _buffer:
        return
    with open(_path, "a", encoding="utf-8") as file:
        for _ in range(len(_buffer)):
            stage, message, (mono_ns, wall_ns) = _buffer.popleft()
            for op in message.ops:
                line = {
                    "stage": stage,
                    "source": "server",
                    "origin": op.origin,
                    "lamport": op.lamport,
                    "object": op.object,
                    "kind": op.kind,
                    "mono_ns": mono_ns,
                    "wall_ns": wall_ns,
                }
                file.write(json.dumps(line) + "\n")


def _run_flusher(stop: threading.Event) -> None:
    while not stop.wait(FLUSH_INTERVAL):
        flush()


def configure(path: str | None) -> None:
    """Turn timing on (writing to `path`) or off (None), flushing anything still buffered."""
    global _path, _stop, _thread
    if _stop is not None:
        _stop.set()
        _thread.join(timeout=2)
        flush()
        _stop = _thread = None
    _path = path or None
    if _path is not None:
        _stop = threading.Event()
        _thread = threading.Thread(target=_run_flusher, args=(_stop,), daemon=True)
        _thread.start()


atexit.register(flush)
configure(os.environ.get("COLLAB_TIMING"))
