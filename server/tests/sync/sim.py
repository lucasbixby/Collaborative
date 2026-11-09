"""A reference client and relay for the convergence tests (#21).

`SimClient` behaves like the add-on, written from docs/protocol.md rules 1-3 and 9 rather than
by calling `RoomState`, so agreeing with `RoomState` means something. It's the spec in code:

- A local edit ticks the clock, is applied at once, is recorded as that key's version, and is
  queued to send. A `create` counts as a write of everything it carries (D-081).
- A received op: skip it if it's our own, merge its lamport into the clock, then
  - `create`: ignored if the ID exists or is tombstoned (rule 3), else added, with versions;
  - `delete`: tombstone the ID, even unseen, and drop the object (rule 2);
  - `set`: dropped for a tombstoned or unknown ID (rules 2, 9), else applied only if strictly
    newer by (lamport, origin) than the key's version (rule 1).

`FakeRelay` is rule 8 without sockets: `send` gives each op a `seq` in arrival order, appends
it to the log, and queues the message for every other connected client. Each client's queue is
FIFO in `seq` order, which is what the real relay does (it broadcasts under the room lock), and
the scheduler decides which client's queue moves next. A reconnecting client gets catch-up:
`RoomState(log).to_ops()`, applied like any received ops, before anything live.
"""

import copy
from collections import deque

from app.sync.conflicts import RoomState

PROPERTIES = ("location", "rotation", "scale", "name")
TRIANGLE = {"vertices": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], "faces": [[0, 1, 2]]}


def ops_message(ops: list[dict]) -> dict:
    return {"v": 1, "type": "ops", "ops": ops}


class SimClient:
    def __init__(self, origin: str) -> None:
        self.origin = origin
        self.clock = 0
        self.scene: dict[str, dict] = {}  # collab_id -> {name, location, rotation, scale}
        self.versions: dict[tuple[str, str], tuple[int, str]] = {}
        self.tombstones: set[str] = set()
        self.outbox: list[dict] = []  # ops edited but not sent yet

    # -- local edits -----------------------------------------------------------------------

    def _tick(self) -> int:
        self.clock += 1
        return self.clock

    def create(self, collab_id: str, name: str, location=(0.0, 0.0, 0.0)) -> None:
        lamport = self._tick()
        values = {
            "name": name,
            "location": list(location),
            "rotation": {"mode": "XYZ", "values": [0.0, 0.0, 0.0]},
            "scale": [1.0, 1.0, 1.0],
        }
        self.scene[collab_id] = copy.deepcopy(values)
        for prop in PROPERTIES:
            self.versions[(collab_id, prop)] = (lamport, self.origin)
        self.outbox.append(
            {
                "kind": "create",
                "object": collab_id,
                "lamport": lamport,
                "origin": self.origin,
                "name": name,
                "object_type": "MESH",
                "collection": "Scene Collection",
                "transform": {key: values[key] for key in ("location", "rotation", "scale")},
                "mesh": TRIANGLE,
            }
        )

    def set(self, collab_id: str, prop: str, value) -> bool:
        """Edit an object this client has. Returns False (and does nothing) if it hasn't."""
        if collab_id not in self.scene:
            return False
        lamport = self._tick()
        self.scene[collab_id][prop] = copy.deepcopy(value)
        self.versions[(collab_id, prop)] = (lamport, self.origin)
        op = {"kind": "set", "object": collab_id, "property": prop, "value": value}
        self.outbox.append({**op, "lamport": lamport, "origin": self.origin})
        return True

    def delete(self, collab_id: str) -> bool:
        if collab_id not in self.scene:
            return False
        self.tombstones.add(collab_id)
        del self.scene[collab_id]
        self.outbox.append(
            {"kind": "delete", "object": collab_id, "lamport": self._tick(), "origin": self.origin}
        )
        return True

    def take_messages(self) -> list[dict]:
        """The outbox as messages, the way detect sends: each `create` alone, then the rest in
        one batch with one `set` per (object, property), the latest (rule 6)."""
        creates = [op for op in self.outbox if op["kind"] == "create"]
        rest: dict[tuple, dict] = {}
        for op in self.outbox:
            if op["kind"] == "set":
                rest[(op["object"], op["property"])] = op
            elif op["kind"] == "delete":
                rest[(op["object"], "delete")] = op
        self.outbox = []
        messages = [ops_message([op]) for op in creates]
        if rest:
            messages.append(ops_message(sorted(rest.values(), key=lambda op: op["lamport"])))
        return messages

    # -- receiving -------------------------------------------------------------------------

    def receive(self, message: dict) -> None:
        for op in message["ops"]:
            self._apply(op)

    def _apply(self, op: dict) -> None:
        if op["origin"] == self.origin:
            return
        self.clock = max(self.clock, op["lamport"])
        collab_id, op_id = op["object"], (op["lamport"], op["origin"])
        if op["kind"] == "delete":
            self.tombstones.add(collab_id)
            self.scene.pop(collab_id, None)
        elif op["kind"] == "create":
            if collab_id in self.scene or collab_id in self.tombstones:
                return
            self.scene[collab_id] = {"name": op["name"], **copy.deepcopy(op["transform"])}
            for prop in PROPERTIES:
                self.versions[(collab_id, prop)] = op_id
        elif op["kind"] == "set":
            if collab_id in self.tombstones or collab_id not in self.scene:
                return
            key = (collab_id, op["property"])
            if key in self.versions and op_id <= self.versions[key]:
                return
            self.scene[collab_id][op["property"]] = copy.deepcopy(op["value"])
            self.versions[key] = op_id


def scene_of(state: RoomState) -> dict[str, dict]:
    """The scene a room's state describes: each created object with its create's values, then
    its winning sets. Read straight off `to_ops()`, not through a SimClient."""
    scene: dict[str, dict] = {}
    for op in state.to_ops():
        if op["kind"] == "create":
            scene[op["object"]] = {"name": op["name"], **copy.deepcopy(op["transform"])}
    for op in state.to_ops():
        if op["kind"] == "set" and op["object"] in scene:
            scene[op["object"]][op["property"]] = copy.deepcopy(op["value"])
    return scene


class FakeRelay:
    def __init__(self) -> None:
        self.log: list[dict] = []  # every op, in seq order (seq = index + 1)
        self.queues: dict[str, deque[dict]] = {}  # origin -> messages not yet delivered

    def connect(self, client: SimClient) -> list[dict]:
        """Join the room: the catch-up messages, then live messages from here on."""
        self.queues[client.origin] = deque()
        return [ops_message([op]) for op in self.state().to_ops()]

    def disconnect(self, client: SimClient) -> None:
        self.queues.pop(client.origin, None)  # anything still queued for it is lost

    def connected(self, client: SimClient) -> bool:
        return client.origin in self.queues

    def send(self, sender: SimClient, message: dict, *, fail: bool = False) -> None:
        """Save, then forward to everyone else. `fail` is D-070: the write fails, so it's
        neither logged nor forwarded (the sender only gets an `error`)."""
        if fail:
            return
        self.log.extend(copy.deepcopy(message["ops"]))
        for origin, queue in self.queues.items():
            if origin != sender.origin:
                queue.append(copy.deepcopy(message))

    def state(self) -> RoomState:
        return RoomState().apply_all(copy.deepcopy(self.log))
