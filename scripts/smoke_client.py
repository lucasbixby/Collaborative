"""Test client for docker_smoke.sh. It runs inside the container, so the smoke test needs nothing
on the host but Docker and curl; `websockets` comes with uvicorn[standard].

    relay <room>   A sends a create and two sets, B must receive all three, A must get no echo
    hold <room>    stay connected until the server closes the connection
"""

import asyncio
import json
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


async def relay(room: str) -> int:
    uri = f"{BASE_URL}/{room}"
    async with websockets.connect(uri) as sender, websockets.connect(uri) as receiver:
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
    async with websockets.connect(f"{BASE_URL}/{room}") as ws:
        print("connected", flush=True)
        await ws.wait_closed()
        print(f"closed by the server with code {ws.close_code}")
    return 0


if __name__ == "__main__":
    command = {"relay": relay, "hold": hold}[sys.argv[1]]
    sys.exit(asyncio.run(command(sys.argv[2])))
