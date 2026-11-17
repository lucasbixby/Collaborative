"""Order operations and decide which value wins (docs/protocol.md rule 1).

Pure Python, no `bpy`. One clock and one `Versions` are shared: detect.py stamps and records
what it sends, apply.py merges and checks what it receives. `tombstones` holds the IDs this
client has deleted or seen deleted; an ID in it is never used again.
"""

OpId = tuple[int, str]  # (lamport, origin): unique per operation, and its ordering key


def newer(a: OpId, b: OpId) -> bool:
    """Whether `a` is ordered after `b`: higher lamport wins; a tie goes to the larger
    `origin` (string comparison), per docs/protocol.md rule 1."""
    return a > b


class LamportClock:
    """A client's own Lamport counter. It never goes backwards, not even across leaving and
    rejoining: a reset would let new edits lose to older ones under last-writer-wins."""

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
    """The `(lamport, origin)` last sent or applied for each `(collab_id, property)`, which an
    incoming operation is checked against."""

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
tombstones: set[str] = set()
