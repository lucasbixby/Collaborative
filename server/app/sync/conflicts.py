"""A room's current state, folded from its operations (#20).

`RoomState` applies operations in `seq` order with the same rules the add-on uses
(docs/protocol.md rules 1–3), so the state it ends with is what every client that saw the
same operations ends with. Pure Python on plain op dicts (validated JSON from the log), with
no database or sockets, so it can be tested alone and #21's convergence tests can build on it.

Rules (D-081):
- `set`: per (object, property), the op with the highest (lamport, origin) wins, the same
  comparison as the add-on's `ordering.newer`.
- `create`: the first one for an ID wins (IDs are UUIDs, so a repeat is a retry). It also
  counts as a write of `location`, `rotation`, `scale` and `name` at its own (lamport, origin),
  so a `set` older than the object's `create` loses.
- `delete`: the ID is tombstoned, its `create` and `set`s are dropped, and every later op for
  it is ignored, including a `create`. Deletes win whatever their timestamp (D-026). Of
  several deletes for one ID, the oldest by (lamport, origin) is kept.
"""

import json

OpId = tuple[int, str]  # (lamport, origin)
CREATE_PROPERTIES = ("location", "rotation", "scale", "name")


def op_id(op: dict) -> OpId:
    return (op["lamport"], op["origin"])


class RoomState:
    def __init__(self) -> None:
        # Insertion order is kept throughout, so `to_ops` is deterministic.
        self._creates: dict[str, dict] = {}
        self._sets: dict[tuple[str, str], dict] = {}
        self._deletes: dict[str, dict] = {}  # the oldest `delete` for each tombstone

    def apply(self, op: dict) -> None:
        """Fold one operation in. Ops must come in `seq` order."""
        collab_id = op["object"]
        kind = op["kind"]
        tombstone = self._deletes.get(collab_id)
        if tombstone is not None:
            # Keep the oldest delete, so the state doesn't depend on which arrived first.
            if kind == "delete" and op_id(op) < op_id(tombstone):
                self._deletes[collab_id] = op
            return
        if kind == "delete":
            self._deletes[collab_id] = op
            self._creates.pop(collab_id, None)
            for key in [key for key in self._sets if key[0] == collab_id]:
                del self._sets[key]
        elif kind == "create":
            if collab_id in self._creates:
                return
            self._creates[collab_id] = op
            # A set that arrived before its create, but is older than it, loses to it.
            for prop in CREATE_PROPERTIES:
                key = (collab_id, prop)
                if key in self._sets and op_id(self._sets[key]) < op_id(op):
                    del self._sets[key]
        elif kind == "set":
            create = self._creates.get(collab_id)
            if create is not None and op_id(op) < op_id(create):
                return
            key = (collab_id, op["property"])
            current = self._sets.get(key)
            if current is None or op_id(op) > op_id(current):
                self._sets[key] = op

    def apply_all(self, ops) -> "RoomState":
        for op in ops:
            self.apply(op)
        return self

    def to_ops(self) -> list[dict]:
        """The state as ordinary ops, each with its original lamport and origin: every
        `create`, then the winning `set`s, then one `delete` per tombstone, so a client still
        holding a deleted object removes it and remembers the tombstone."""
        return [*self._creates.values(), *self._sets.values(), *self._deletes.values()]

    def to_json(self) -> str:
        return json.dumps({"ops": self.to_ops()}, separators=(",", ":"))

    @classmethod
    def from_json(cls, text: str) -> "RoomState":
        """Folding `to_ops()` again rebuilds the same state, since it holds no op that loses."""
        return cls().apply_all(json.loads(text)["ops"])

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RoomState) and self.to_ops() == other.to_ops()
