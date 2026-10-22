"""Order operations and decide which value wins (D-006, protocol rule 1; #8 / #9).

Pure Python, no `bpy`, so it's unit-testable on its own. `detect.py` stamps its outgoing
operations with `clock.tick()` and records them in `versions`; `apply.py` merges an
incoming operation's timestamp with `clock.observe()` and checks it against `versions`
before applying it. One shared clock and one shared `Versions`, used by both.
"""

OpId = tuple[int, str]  # (lamport, origin): unique per operation, and its ordering key


def newer(a: OpId, b: OpId) -> bool:
    """Whether `a` is ordered after `b`: higher lamport wins; a tie goes to the larger
    `origin` (string comparison), per docs/protocol.md rule 1."""
    return a > b


class LamportClock:
    """A client's own Lamport counter.

    Never goes backwards, including across `detect.stop()` / `start()`: resetting it on
    restart (the original behaviour, flagged in the #5 review) would let a restarted
    client's new edits lose to its own or others' older ones under last-writer-wins.
    """

    def __init__(self) -> None:
        self._value = 0

    def tick(self) -> int:
        """A new local operation: advance the counter and return its timestamp."""
        self._value += 1
        return self._value

    def observe(self, n: int) -> None:
        """A received timestamp: merge it in (`max`), never moving backwards."""
        self._value = max(self._value, n)


class Versions:
    """Last-writer-wins state (#9): the `(lamport, origin)` last sent or applied for each
    `(collab_id, property)` key, so an incoming operation can be checked against it."""

    def __init__(self) -> None:
        self._last: dict[tuple[str, str], OpId] = {}

    def should_apply(self, key: tuple[str, str], op_id: OpId) -> bool:
        """True if `op_id` is newer than what's recorded for `key` (or nothing is)."""
        last = self._last.get(key)
        return last is None or newer(op_id, last)

    def record(self, key: tuple[str, str], op_id: OpId) -> None:
        self._last[key] = op_id


clock = LamportClock()
versions = Versions()
