"""Convergence through the real relay (#21): signed-in editors on real sockets.

Three editors (the #16-#18 accounts and invites) each drive a `SimClient` (tests/sync/sim.py),
making random edits and sending them over their own socket while the others haven't heard yet.
Mid-run one disconnects, keeps editing offline, and reconnects (catch-up); at the end a fourth
editor joins late. At quiescence every scene, the late joiner's and the REST snapshot's agree.

No sleeps: each peer counts the messages it's owed (one per message another connected peer
sent) and reads exactly that many, so a lost message shows up as a pytest-timeout, not a flake.
Peers quiesce before anyone disconnects or (re)joins, so no message is in flight across one.
Only editors take part: a viewer's ops are refused (#17), so they can't affect anyone's scene.
"""

import json
import random
from contextlib import ExitStack

import pytest

from app.sync.conflicts import RoomState
from tests.accounts import bearer, ensure_room, token_for
from tests.catchup import read_catch_up
from tests.sync.sim import SimClient, scene_of
from tests.sync.test_convergence import ORIGINS, PROPS, _value

ROOM = "converge"
STEPS = 150


class _Peer:
    def __init__(self, test_client, headers: dict, origin: str, everyone: list) -> None:
        self.test_client = test_client
        self.headers = headers
        self.sim = SimClient(origin)
        self.everyone = everyone
        self.owed = 0  # messages other peers sent since this one connected, not yet read
        self.stack: ExitStack | None = None
        self.ws = None

    def connect(self) -> None:
        self.stack = ExitStack()
        self.ws = self.stack.enter_context(
            self.test_client.websocket_connect(f"/ws/rooms/{ROOM}", headers=self.headers)
        )
        catch_up, _seq = read_catch_up(self.ws)
        for message in catch_up:
            self.sim.receive(message)

    def disconnect(self) -> None:
        self.stack.close()
        self.stack, self.ws, self.owed = None, None, 0

    def send(self) -> None:
        if self.ws is None:
            return  # offline: edits wait in the outbox, as in the add-on
        for message in self.sim.take_messages():
            self.ws.send_text(json.dumps(message))
            for other in self.everyone:
                if other is not self and other.ws is not None:
                    other.owed += 1

    def read_one(self) -> None:
        message = json.loads(self.ws.receive_text())
        assert message["type"] == "ops", message  # an `error` means the relay refused an edit
        self.sim.receive(message)
        self.owed -= 1


def _quiesce(peers: list[_Peer]) -> None:
    while any(p.ws is not None and (p.sim.outbox or p.owed) for p in peers):
        for peer in peers:
            peer.send()
        for peer in peers:
            while peer.ws is not None and peer.owed:
                peer.read_one()


# Few objects alive at once, for conflicts; IDs are never reused, so a deleted one is replaced.
POOL = [f"{n:08x}-0000-4000-8000-000000000000" for n in range(1, 40)]


def _edit(rng: random.Random, sim: SimClient, n: int, created: set[str]) -> None:
    known = [obj for obj in POOL if obj in sim.scene]
    roll = rng.random()
    if roll < 0.1 or len(known) < 2:
        obj = next(obj for obj in POOL if obj not in created)
        created.add(obj)
        sim.create(obj, f"New-{n}")
    elif roll < 0.93:
        prop = rng.choice(PROPS)
        sim.set(rng.choice(known), prop, _value(prop, n))
    else:
        sim.delete(rng.choice(known))


@pytest.fixture
def editors(client):
    """Headers for tester (the room's owner) and four invited editors."""
    ensure_room(client, ROOM)
    code = client.post(f"/api/rooms/{ROOM}/invites", json={"role": "editor"}).json()["code"]
    headers = [dict(client.headers)]
    for name in ("bob", "carol", "dave"):
        token = token_for(client, name)
        assert client.post(f"/api/rooms/join/{code}", headers=bearer(token)).status_code == 200
        headers.append(bearer(token))
    return headers


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_editors_converge_through_the_real_relay(client, editors, seed):
    rng = random.Random(seed)
    peers: list[_Peer] = []
    peers.extend(_Peer(client, editors[i], ORIGINS[i], peers) for i in range(3))
    created: set[str] = set()
    away = peers[2]
    try:
        for peer in peers:
            peer.connect()
        for n in range(STEPS):
            if n == STEPS // 3:
                _quiesce(peers)  # so nothing it sent is still in flight when it goes
                away.disconnect()
            if n == 2 * STEPS // 3:
                # Nothing in flight either way: a message the server handles after this
                # peer's catch-up reaches it live, uncounted, and the count would be off by one.
                _quiesce(peers)
                away.connect()  # catch-up, then its offline edits go out with the rest
            peer = rng.choice(peers)
            roll = rng.random()
            if roll < 0.45:
                _edit(rng, peer.sim, n, created)
            elif roll < 0.75:
                peer.send()
            elif peer.ws is not None and peer.owed:
                peer.read_one()
        _quiesce(peers)

        late = _Peer(client, editors[3], ORIGINS[3], peers)
        late.connect()
        peers.append(late)

        snapshot = client.get(f"/api/rooms/{ROOM}/snapshot").json()
        server = scene_of(RoomState().apply_all(snapshot["ops"]))
        scenes = [peer.sim.scene for peer in peers]
        assert server, "the run should leave something in the room"
        assert snapshot["seq"] >= 40, snapshot["seq"]  # enough traffic to have meant something
        for i, scene in enumerate(scenes):
            assert scene == server, f"seed {seed}: peer {i} differs from the snapshot"
    finally:
        for peer in peers:
            if peer.ws is not None:
                peer.disconnect()
