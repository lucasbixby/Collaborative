"""Test client for docker_smoke.sh. It runs inside the container, so the smoke test needs nothing
on the host but Docker and curl; `websockets` comes with uvicorn[standard].

    relay <room>     A sends a create and two sets, B must receive all three, A must get no echo
    hold <room>      stay connected until the server closes the connection
    refused <room> <code>   the server must close with <code> (4401, 4403) before any catch-up

Signs in with COLLAB_TOKEN (#16), if it's set.
"""

import asyncio
import json
import os
import sys
import uuid

import websockets

BASE_URL = "ws://127.0.0.1:8000/ws/rooms"
TIMEOUT = 5


def _messages() -> list[dict]:
    origin, obj = str(uuid.uuid4()), str(uuid.uuid4())
    common = {"object": obj, "origin": origin}
    create = {
        **common,
        "kind": "create",
        "lamport": 1,
        "name": "SmokeTriangle",
        "object_type": "MESH",
        "collection": "Scene Collection",
        "transform": {
            "location": [0.0, 0.0, 0.0],
            "rotation": {"mode": "XYZ", "values": [0.0, 0.0, 0.0]},
            "scale": [1.0, 1.0, 1.0],
        },
        "mesh": {"vertices": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], "faces": [[0, 1, 2]]},
    }
    moves = [
        {**common, "kind": "set", "lamport": 2, "property": "location", "value": [1.0, 2.0, 3.0]},
        {**common, "kind": "set", "lamport": 3, "property": "scale", "value": [2.0, 2.0, 2.0]},
    ]
    return [{"v": 1, "type": "ops", "ops": [create]}, {"v": 1, "type": "ops", "ops": moves}]


async def _caught_up(ws) -> None:
    """Read the room's catch-up, which every connection starts with (#20), up to `synced`."""
    while json.loads(await asyncio.wait_for(ws.recv(), TIMEOUT)).get("type") != "synced":
        pass


def _connect(room: str):
    token = os.environ.get("COLLAB_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return websockets.connect(f"{BASE_URL}/{room}", additional_headers=headers)


async def relay(room: str) -> int:
    async with _connect(room) as sender, _connect(room) as receiver:
        await _caught_up(sender)
        await _caught_up(receiver)
        messages = _messages()
        for message in messages:
            await sender.send(json.dumps(message))
            received = json.loads(await asyncio.wait_for(receiver.recv(), TIMEOUT))
            if received != message:
                print(f"received something else: {received}", file=sys.stderr)
                return 1
        try:
            echo = await asyncio.wait_for(sender.recv(), 0.5)
        except TimeoutError:
            print("B received all 2 messages (3 operations); A got no echo")
            return 0
        print(f"the sender got something back: {echo}", file=sys.stderr)
        return 1


async def hold(room: str) -> int:
    async with _connect(room) as ws:
        print("connected", flush=True)
        await ws.wait_closed()
        print(f"closed by the server with code {ws.close_code}")
    return 0


async def refused(room: str, code: str) -> int:
    async with _connect(room) as ws:
        try:
            first = await asyncio.wait_for(ws.recv(), TIMEOUT)
        except websockets.exceptions.ConnectionClosed:
            if ws.close_code == int(code):
                print(f"refused with {code}: {ws.close_reason}")
                return 0
            print(f"closed with {ws.close_code}, not {code}", file=sys.stderr)
            return 1
        print(f"got a message instead of a {code} close: {first}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    command = {"relay": relay, "hold": hold, "refused": refused}[sys.argv[1]]
    sys.exit(asyncio.run(command(*sys.argv[2:])))
