"""Convergence under concurrent edits (#21): every client ends with the same scene.

A seeded scheduler runs 2-4 `SimClient`s (tests/sync/sim.py) against a `FakeRelay`, and checks
at quiescence that every client's scene is identical, equals the room's `RoomState` folded from
the log, and equals what a fresh client gets from catch-up alone. Steps are biased toward
conflicts: few objects, bursts where several clients edit one property before anyone hears from
the others (equal clocks, so Lamport ties broken by origin), deletes racing sets, edits to an
object someone just deleted, and disconnects that miss traffic and then catch up.

A failure prints the seed and the shortest trace that still fails; paste the trace into
`_replay` to debug. `COLLAB_CONVERGENCE_SEEDS=N` runs N seeds instead of the CI set.

The second half writes and checks the conformance vectors in tests/vectors/convergence.json at
the repo root: short scripted scenarios, each one client's delivery stream and the scene it
must end with. The add-on's real `apply_message` is run on the same file
(addon/tests/test_convergence_vectors.py), so the model and the real client are held to one
answer. Set COLLAB_REGENERATE_VECTORS=1 to rewrite the file.

Only editors take part: a viewer's ops are refused by the relay (#17), so they never reach
anyone and can't affect convergence.
"""

import json
import os
import random
from pathlib import Path

import pytest

from app.sync.conflicts import RoomState
from tests.sync.sim import FakeRelay, SimClient, ops_message, scene_of

VECTORS = Path(__file__).resolve().parents[3] / "tests" / "vectors" / "convergence.json"
CI_SEEDS = 300
SEEDS = int(os.environ.get("COLLAB_CONVERGENCE_SEEDS", CI_SEEDS))
STEPS = 60

# Origins chosen so that their string order doesn't follow the client index.
ORIGINS = [
    "c0000000-0000-4000-8000-000000000000",
    "a0000000-0000-4000-8000-000000000000",
    "d0000000-0000-4000-8000-000000000000",
    "b0000000-0000-4000-8000-000000000000",
]
OBJECTS = [f"0000000{n}-0000-4000-8000-00000000000{n}" for n in range(1, 5)]
PROPS = ("location", "rotation", "scale", "name")


def _value(prop: str, n: int):
    """A distinct value for step `n`, so any two writes are told apart."""
    if prop == "name":
        return f"Obj-{n}"
    if prop == "rotation":
        mode = "QUATERNION" if n % 3 == 0 else "XYZ"
        values = [1.0, 0.0, 0.0, float(n)] if mode == "QUATERNION" else [float(n), 0.0, 0.0]
        return {"mode": mode, "values": values}
    return [float(n), float(n % 7), 1.0 if prop == "scale" else 0.0]


# -- The scheduler --------------------------------------------------------------------------
# A trace is a list of plain tuples, so it can be printed, shrunk and replayed:
#   ("create", c, obj)  ("set", c, obj, prop, n)  ("delete", c, obj)
#   ("burst", ((c, obj, prop, n), ...))  ("send", c)  ("deliver", c)  ("drop", c)  ("join", c)


def _generate(seed: int) -> list[tuple]:
    rng = random.Random(seed)
    clients = rng.randint(2, 4)
    objects = OBJECTS[: rng.randint(1, 3)]
    sim = _World(clients)
    trace: list[tuple] = []
    for n in range(STEPS):
        c = rng.randrange(clients)
        client = sim.clients[c]
        known = [obj for obj in objects if obj in client.scene]
        roll = rng.random()
        if roll < 0.08 and (unborn := [o for o in objects if o not in sim.created]):
            step = ("create", c, rng.choice(unborn))
        elif roll < 0.30 and known:
            step = ("set", c, rng.choice(known), rng.choice(PROPS), n)
        elif roll < 0.40 and sim.created:
            # Several clients edit one property of one object before hearing from each other.
            obj, prop = rng.choice(sorted(sim.created)), rng.choice(PROPS)
            editors = rng.sample(range(clients), rng.randint(2, clients))
            step = ("burst", tuple((e, obj, prop, n * 10 + i) for i, e in enumerate(editors)))
        elif roll < 0.46 and known:
            step = ("delete", c, rng.choice(known))
        elif roll < 0.66:
            step = ("send", c)
        elif roll < 0.92:
            step = ("deliver", c)
        elif roll < 0.96:
            step = ("drop", c)
        else:
            step = ("join", c)
        sim.do(step)
        trace.append(step)
    return [(clients,), *trace]


class _World:
    def __init__(self, clients: int) -> None:
        self.relay = FakeRelay()
        self.clients = [SimClient(ORIGINS[i]) for i in range(clients)]
        self.created: set[str] = set()
        for client in self.clients:
            self.relay.connect(client)

    def do(self, step: tuple) -> None:
        """Run one step. A step that makes no sense any more (after shrinking) is skipped."""
        kind = step[0]
        if kind == "create":
            _, c, obj = step
            if obj not in self.created:
                self.created.add(obj)
                self.clients[c].create(obj, f"New-{obj[7]}")
        elif kind == "set":
            _, c, obj, prop, n = step
            self.clients[c].set(obj, prop, _value(prop, n))
        elif kind == "burst":
            for c, obj, prop, n in step[1]:
                self.clients[c].set(obj, prop, _value(prop, n))
        elif kind == "delete":
            self.clients[step[1]].delete(step[2])
        elif kind == "send":
            self._send(self.clients[step[1]])
        elif kind == "deliver":
            client = self.clients[step[1]]
            queue = self.relay.queues.get(client.origin)
            if queue:
                client.receive(queue.popleft())
        elif kind == "drop":
            self.relay.disconnect(self.clients[step[1]])
        elif kind == "join":
            self._join(self.clients[step[1]])

    def _send(self, client: SimClient) -> None:
        # Offline, edits wait in the outbox, as they do in the add-on's client.
        if self.relay.connected(client):
            for message in client.take_messages():
                self.relay.send(client, message)

    def _join(self, client: SimClient) -> None:
        if not self.relay.connected(client):
            for message in self.relay.connect(client):
                client.receive(message)

    def settle(self) -> None:
        """Everyone back online, everything sent and delivered."""
        for client in self.clients:
            self._join(client)
        while any(client.outbox for client in self.clients) or any(self.relay.queues.values()):
            for client in self.clients:
                self._send(client)
            for client in self.clients:
                queue = self.relay.queues[client.origin]
                while queue:
                    client.receive(queue.popleft())


def _replay(trace: list[tuple]) -> _World:
    world = _World(trace[0][0])
    for step in trace[1:]:
        world.do(step)
    world.settle()
    return world


def _divergence(trace: list[tuple]) -> str | None:
    """What's wrong at quiescence, or None if every check holds."""
    world = _replay(trace)
    scenes = [client.scene for client in world.clients]
    for i, scene in enumerate(scenes[1:], start=1):
        if scene != scenes[0]:
            return f"client 0 and client {i} differ:\n  {scenes[0]}\n  {scene}"
    server = scene_of(world.relay.state())
    if scenes[0] != server:
        return f"clients differ from the server's RoomState:\n  {scenes[0]}\n  {server}"
    fresh = SimClient("ffffffff-0000-4000-8000-000000000000")
    for message in world.relay.connect(fresh):
        fresh.receive(message)
    if fresh.scene != server:
        return f"a fresh client's catch-up differs:\n  {fresh.scene}\n  {server}"
    return None


def _shrink(trace: list[tuple]) -> list[tuple]:
    """Remove steps (halves first, then one at a time) while the trace still fails."""
    chunk = max(1, (len(trace) - 1) // 2)
    while chunk >= 1:
        i = 1
        while i < len(trace):
            candidate = trace[:i] + trace[i + chunk :]
            if _divergence(candidate) is not None:
                trace = candidate
            else:
                i += chunk
        chunk //= 2
    return trace


def test_clients_converge_under_random_concurrent_edits():
    for seed in range(SEEDS):
        trace = _generate(seed)
        problem = _divergence(trace)
        if problem is not None:
            shortest = _shrink(trace)
            pytest.fail(
                f"seed {seed} diverged: {problem}\n"
                f"shortest failing trace ({len(shortest) - 1} steps), replay with _replay():\n"
                + "\n".join(f"  {step!r}," for step in shortest)
            )


def test_the_scenarios_hit_every_conflict_case():
    # Guards the generator's bias: if a change made conflicts rare, the test above would
    # still pass while proving much less.
    seen = {"tie": 0, "delete_vs_set": 0, "missed_while_away": 0, "deleted_then_edited": 0}
    for seed in range(min(SEEDS, CI_SEEDS)):
        world = _replay(_generate(seed))
        ops = world.relay.log
        by_key: dict[tuple, set] = {}
        for op in ops:
            if op["kind"] == "set":
                by_key.setdefault((op["object"], op["property"], op["lamport"]), set()).add(op["origin"])
        seen["tie"] += any(len(origins) > 1 for origins in by_key.values())
        deleted = {op["object"]: i for i, op in enumerate(ops) if op["kind"] == "delete"}
        seen["deleted_then_edited"] += any(
            op["kind"] == "set" and op["object"] in deleted and i > deleted[op["object"]]
            for i, op in enumerate(ops)
        )
        seen["delete_vs_set"] += any(
            op["kind"] == "set" and op["object"] in deleted for op in ops
        )
    trace_steps = [step for seed in range(50) for step in _generate(seed)[1:]]
    seen["missed_while_away"] = sum(step[0] == "join" for step in trace_steps)
    assert all(count >= 10 for count in seen.values()), seen


def test_the_shrinker_finds_a_short_trace(monkeypatch):
    # Break the model on purpose (a Lamport tie goes to whichever arrives last, ignoring the
    # origin) and check that a failure is found and comes back short enough to read.
    original = SimClient._apply

    def ignore_origin_on_ties(self, op):
        key = (op["object"], op.get("property"))
        if op["kind"] == "set" and key in self.versions:
            lamport, origin = self.versions[key]
            if op["lamport"] == lamport and op["origin"] != self.origin:
                self.versions[key] = (lamport - 1, origin)
        original(self, op)

    monkeypatch.setattr(SimClient, "_apply", ignore_origin_on_ties)
    failing = next(_generate(s) for s in range(SEEDS) if _divergence(_generate(s)))
    shortest = _shrink(failing)
    assert _divergence(shortest) is not None
    assert len(shortest) - 1 <= 12, shortest


# -- Known limits ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="D-070: a failed write leaves its sender ahead of the room")
def test_a_failed_write_still_converges():
    relay = FakeRelay()
    a, b = SimClient(ORIGINS[0]), SimClient(ORIGINS[1])
    for client in (a, b):
        relay.connect(client)
    a.create(OBJECTS[0], "Cube")
    relay.send(a, a.take_messages()[0])
    b.receive(relay.queues[b.origin].popleft())

    a.set(OBJECTS[0], "location", [5.0, 0.0, 0.0])
    relay.send(a, a.take_messages()[0], fail=True)  # the server couldn't save it
    relay.disconnect(a)  # and a reconnect's catch-up doesn't repair it either
    for message in relay.connect(a):
        a.receive(message)

    assert a.scene == b.scene


def test_sets_for_an_object_that_was_never_created():
    # Objects from a shared .blend before #15 have IDs but no `create` in the log. Clients
    # that have the object apply its sets; a client without it drops them (rule 9), and
    # catch-up can't build it, because the log has nothing to build it from. RoomState keeps
    # the sets (D-081), but there's no object for them, so `scene_of` shows none.
    relay = FakeRelay()
    shared = {"name": "Cube", "location": [0.0, 0.0, 0.0],
              "rotation": {"mode": "XYZ", "values": [0.0, 0.0, 0.0]}, "scale": [1.0, 1.0, 1.0]}
    a, b = SimClient(ORIGINS[0]), SimClient(ORIGINS[1])
    for client in (a, b):
        client.scene[OBJECTS[0]] = json.loads(json.dumps(shared))  # both opened the .blend
        relay.connect(client)
    a.set(OBJECTS[0], "location", [3.0, 0.0, 0.0])
    relay.send(a, a.take_messages()[0])
    b.receive(relay.queues[b.origin].popleft())

    late = SimClient(ORIGINS[2])
    for message in relay.connect(late):
        late.receive(message)

    assert a.scene == b.scene and b.scene[OBJECTS[0]]["location"] == [3.0, 0.0, 0.0]
    assert late.scene == {} == scene_of(relay.state())
    assert [op["kind"] for op in relay.state().to_ops()] == ["set"]


# -- Conformance vectors ---------------------------------------------------------------------

OBSERVER = "e0000000-0000-4000-8000-000000000000"
X, Y = OBJECTS[0], OBJECTS[1]


class _Script:
    """A scripted scenario: clients edit, send and deliver by hand, and an observer that never
    edits records exactly what it's delivered, in order. That stream and the observer's final
    scene are the vector."""

    def __init__(self, clients: int = 2, observer_online: bool = True) -> None:
        self.relay = FakeRelay()
        self.clients = [SimClient(ORIGINS[i]) for i in range(clients)]
        for client in self.clients:
            self.relay.connect(client)
        self.observer = SimClient(OBSERVER)
        self.stream: list[dict] = []
        if observer_online:
            self.join_observer()

    def send(self, c: int) -> None:
        for message in self.clients[c].take_messages():
            self.relay.send(self.clients[c], message)

    def deliver_all(self, c: int) -> None:
        queue = self.relay.queues[self.clients[c].origin]
        while queue:
            self.clients[c].receive(queue.popleft())

    def observe(self) -> None:
        queue = self.relay.queues.get(OBSERVER)
        while queue:
            self._feed(queue.popleft())

    def join_observer(self) -> None:
        for message in self.relay.connect(self.observer):
            self._feed(message)

    def _feed(self, message: dict) -> None:
        self.stream.append(message)
        self.observer.receive(message)


def _lww_later_lamport():
    s = _Script()
    a, b = s.clients
    a.create(X, "Cube")
    s.send(0)
    s.deliver_all(1)
    b.set(X, "location", [1.0, 0.0, 0.0])
    s.send(1)
    s.deliver_all(0)
    a.set(X, "location", [2.0, 0.0, 0.0])  # a has seen b's, so this one is later
    s.send(0)
    s.observe()
    return s


def _tie(winner_first: bool):
    def scenario():
        s = _Script()
        a, b = s.clients  # a's origin (c...) is larger than b's (a...)
        a.create(X, "Cube")
        s.send(0)
        s.deliver_all(1)
        a.set(X, "location", [1.0, 0.0, 0.0])
        b.set(X, "location", [2.0, 0.0, 0.0])  # the same lamport: a's origin wins
        s.send(0 if winner_first else 1)
        s.send(1 if winner_first else 0)
        s.observe()
        return s

    return scenario


def _older_arrives_later():
    s = _Script()
    a, b = s.clients
    a.create(X, "Cube")
    s.send(0)
    s.deliver_all(1)
    for n in range(3):
        a.set(X, "scale", [float(n + 2)] * 3)  # a's clock runs ahead
    b.set(X, "scale", [9.0, 9.0, 9.0])  # older: it hasn't heard a's
    s.send(0)
    s.send(1)
    s.observe()
    return s


def _delete_beats_a_later_set():
    s = _Script()
    a, b = s.clients
    a.create(X, "Cube")
    s.send(0)
    s.deliver_all(1)
    for n in range(4):
        b.set(X, "location", [float(n), 0.0, 0.0])  # b's last set has a higher lamport
    a.delete(X)
    s.send(0)
    s.send(1)
    s.observe()
    return s


def _set_then_delete():
    s = _Script()
    a, b = s.clients
    a.create(X, "Cube")
    s.send(0)
    s.deliver_all(1)
    b.set(X, "location", [4.0, 0.0, 0.0])
    s.send(1)
    a.delete(X)
    s.send(0)
    s.observe()
    return s


def _edit_after_someone_deleted():
    s = _Script(clients=3)
    a, b, c = s.clients
    a.create(X, "Cube")
    a.create(Y, "Sphere")
    s.send(0)
    s.deliver_all(1)
    s.deliver_all(2)
    b.delete(X)
    s.send(1)
    s.deliver_all(0)  # a has heard; c hasn't
    c.set(X, "name", "Renamed")
    c.set(Y, "location", [1.0, 1.0, 1.0])
    s.send(2)
    s.observe()
    return s


def _two_deletes():
    s = _Script()
    a, b = s.clients
    a.create(X, "Cube")
    s.send(0)
    s.deliver_all(1)
    a.delete(X)
    b.delete(X)
    s.send(1)
    s.send(0)
    s.observe()
    return s


def _independent_properties():
    s = _Script(clients=3)
    a, b, c = s.clients
    a.create(X, "Cube")
    s.send(0)
    s.deliver_all(1)
    s.deliver_all(2)
    a.set(X, "location", [1.0, 2.0, 3.0])
    b.set(X, "scale", [2.0, 2.0, 2.0])
    c.set(X, "name", "Shared")
    for i in (2, 0, 1):
        s.send(i)
    s.observe()
    return s


def _rotation_modes():
    s = _Script()
    a, b = s.clients
    a.create(X, "Cube")
    s.send(0)
    s.deliver_all(1)
    a.set(X, "rotation", {"mode": "XYZ", "values": [0.5, 0.0, 0.0]})
    b.set(X, "rotation", {"mode": "QUATERNION", "values": [0.7071, 0.7071, 0.0, 0.0]})
    s.send(1)
    s.send(0)
    s.observe()
    return s


def _name_conflict():
    s = _Script()
    a, b = s.clients
    a.create(X, "Cube")
    s.send(0)
    s.deliver_all(1)
    b.set(X, "name", "FromB")
    a.set(X, "name", "FromA")
    s.send(1)
    s.send(0)
    s.observe()
    return s


def _three_way_tie():
    s = _Script(clients=3)
    a, b, c = s.clients
    a.create(X, "Cube")
    s.send(0)
    s.deliver_all(1)
    s.deliver_all(2)
    a.set(X, "location", [1.0, 0.0, 0.0])
    b.set(X, "location", [2.0, 0.0, 0.0])
    c.set(X, "location", [3.0, 0.0, 0.0])  # all at lamport 2; d... origin wins
    for i in (0, 2, 1):
        s.send(i)
    s.observe()
    return s


def _catch_up_after_missing_traffic():
    s = _Script()
    a, b = s.clients
    a.create(X, "Cube")
    a.create(Y, "Sphere")
    s.send(0)
    s.observe()
    s.relay.disconnect(s.observer)  # misses everything below
    s.deliver_all(1)
    b.set(X, "location", [7.0, 0.0, 0.0])
    a.delete(Y)
    s.send(0)
    s.send(1)
    s.join_observer()  # catch-up repeats X's create (ignored), then the set and Y's delete
    return s


def _late_joiner():
    s = _Script(observer_online=False)
    a, b = s.clients
    a.create(X, "Cube")
    a.create(Y, "Sphere")
    s.send(0)
    s.deliver_all(1)
    b.set(X, "scale", [3.0, 3.0, 3.0])
    b.delete(Y)
    s.send(1)
    s.join_observer()
    return s


def _delete_then_create_in_catch_up():
    # Catch-up of a room where X was created and deleted holds only the delete; the observer
    # tombstones an ID it never had, then a slow client's late set for it is ignored.
    s = _Script(observer_online=False)
    a, b = s.clients
    a.create(X, "Cube")
    s.send(0)
    s.deliver_all(1)
    a.delete(X)
    s.send(0)
    s.join_observer()
    b.set(X, "location", [1.0, 0.0, 0.0])
    s.send(1)
    s.observe()
    return s


def _messages_only(*messages):
    """A scenario that can't be reached through the relay, given as a delivery stream."""

    def scenario():
        s = _Script(clients=0)
        for message in messages:
            s._feed(message)
        return s

    return scenario


def _create(obj, name, lamport, origin=ORIGINS[0], location=(0.0, 0.0, 0.0)):
    client = SimClient(origin)
    client.clock = lamport - 1
    client.create(obj, name, location)
    return client.outbox[0]


def _op(kind, obj, lamport, origin=ORIGINS[1], **extra):
    return {"kind": kind, "object": obj, "lamport": lamport, "origin": origin, **extra}


VECTOR_SCENARIOS = {
    "lww_later_lamport_wins": ("rule 1", _lww_later_lamport),
    "tie_larger_origin_wins_winner_first": ("rule 1, Lamport tie", _tie(winner_first=True)),
    "tie_larger_origin_wins_winner_last": ("rule 1, Lamport tie", _tie(winner_first=False)),
    "older_set_arriving_later_is_skipped": ("rule 1", _older_arrives_later),
    "delete_beats_a_later_set": ("rule 2, delete racing set", _delete_beats_a_later_set),
    "set_then_delete": ("rule 2", _set_then_delete),
    "edit_after_someone_deleted": ("rule 2, editing a deleted object", _edit_after_someone_deleted),
    "two_deletes_of_one_object": ("rules 2-3", _two_deletes),
    "independent_properties_all_kept": ("rule 1, per (object, property)", _independent_properties),
    "rotation_mode_conflict": ("rule 1, rotation", _rotation_modes),
    "name_conflict": ("rule 1, name", _name_conflict),
    "three_way_tie": ("rule 1, Lamport tie", _three_way_tie),
    "catch_up_after_missing_traffic": ("catch-up, rule 3 repeat create", _catch_up_after_missing_traffic),
    "late_joiner_catch_up_only": ("catch-up", _late_joiner),
    "delete_only_in_catch_up_then_late_set": ("rule 2, delete racing create", _delete_then_create_in_catch_up),
    "delete_arrives_before_create": (
        "rule 2, delete racing create",
        _messages_only(
            ops_message([_op("delete", X, 2)]),
            ops_message([_create(X, "Cube", 1)]),
        ),
    ),
    "repeated_create_is_ignored": (
        "rule 3",
        _messages_only(
            ops_message([_create(X, "Cube", 1)]),
            ops_message([_op("set", X, 2, property="location", value=[1.0, 0.0, 0.0])]),
            ops_message([_create(X, "Cube", 1)]),
        ),
    ),
    "set_older_than_its_create_loses": (
        "D-081, create counts as a write",
        _messages_only(
            ops_message([_create(X, "Cube", 5)]),
            ops_message([_op("set", X, 3, property="location", value=[9.0, 0.0, 0.0])]),
            ops_message([_op("set", X, 6, property="scale", value=[2.0, 2.0, 2.0])]),
        ),
    ),
    "set_for_unknown_object_is_dropped": (
        "rule 9",
        _messages_only(
            ops_message([_op("set", Y, 4, property="location", value=[1.0, 0.0, 0.0])]),
            ops_message([_create(X, "Cube", 1)]),
        ),
    ),
    "tie_on_create_values": (
        "D-081, a set tied with its create",
        _messages_only(
            ops_message([_create(X, "Cube", 3, origin=ORIGINS[3])]),  # b...
            ops_message([_op("set", X, 3, origin=ORIGINS[0], property="name", value="Wins")]),
            ops_message([_op("set", X, 3, origin=ORIGINS[1], property="scale", value=[5.0, 5.0, 5.0])]),
        ),
    ),
}


def _same_name_on_two_objects():
    s = _Script()
    a, b = s.clients
    a.create(X, "Cube")
    a.create(Y, "Sphere")
    s.send(0)
    s.deliver_all(1)
    a.set(X, "name", "Shared")
    b.set(Y, "name", "Shared")  # a different object, the same name
    s.send(0)
    s.send(1)
    s.observe()
    return s


VECTOR_SCENARIOS["same_name_on_two_objects"] = ("rule 1, name", _same_name_on_two_objects)

# Where the real add-on is known to disagree with the model. The add-on test expects these to
# fail (strict xfail), so a fix shows up as soon as it lands. See the devlog's #21 entry.
KNOWN_DIVERGENCES = {
    "same_name_on_two_objects": (
        "Blender keeps object names unique: the second object to take a name becomes "
        "'Shared.001', and which one is second depends on arrival order, so clients differ"
    ),
}


def _vectors() -> dict:
    scenarios = []
    for name, (covers, build) in VECTOR_SCENARIOS.items():
        s = build()
        scenario = {"name": name, "covers": covers, "messages": s.stream, "expected": s.observer.scene}
        if name in KNOWN_DIVERGENCES:
            scenario["known_divergence"] = KNOWN_DIVERGENCES[name]
        scenarios.append(scenario)
    return {
        "about": "Generated by server/tests/sync/test_convergence.py (#21); "
        "COLLAB_REGENERATE_VECTORS=1 rewrites it. Each scenario is one client's delivery "
        "stream and the scene it must end with.",
        "scenarios": scenarios,
    }


def _encode(vectors: dict) -> str:
    return json.dumps(vectors, indent=1) + "\n"


def test_the_vector_file_is_up_to_date():
    expected = _encode(_vectors())
    if os.environ.get("COLLAB_REGENERATE_VECTORS"):
        VECTORS.parent.mkdir(parents=True, exist_ok=True)
        VECTORS.write_text(expected)
    assert VECTORS.exists(), "run with COLLAB_REGENERATE_VECTORS=1 to write it"
    assert VECTORS.read_text() == expected, "stale: rerun with COLLAB_REGENERATE_VECTORS=1"


@pytest.mark.parametrize("scenario", json.loads(VECTORS.read_text())["scenarios"] if VECTORS.exists() else [], ids=lambda s: s["name"])
def test_room_state_folds_each_vector_to_its_expected_scene(scenario):
    ops = [op for message in scenario["messages"] for op in message["ops"]]
    assert scene_of(RoomState().apply_all(ops)) == scenario["expected"]


def test_scripted_scenarios_also_converge():
    # Each script, settled, passes the same checks as the random runs.
    for name, (_covers, build) in VECTOR_SCENARIOS.items():
        s = build()
        if not s.clients:
            continue
        for c in range(len(s.clients)):
            s.send(c)
        for c in range(len(s.clients)):
            s.deliver_all(c)
        s.observe()
        scenes = [client.scene for client in s.clients] + [s.observer.scene]
        assert all(scene == scenes[0] for scene in scenes), name
        assert scenes[0] == scene_of(s.relay.state()), name
