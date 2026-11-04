#!/usr/bin/env python3
"""Simulated clients for the load scenario (#24): each adds one object, then moves it steadily.

Needs `websockets`, e.g. server/.venv/bin/python scripts/latency_load.py latency --clients 8
Stops on Ctrl+C or SIGTERM and prints how many messages it managed to send.
"""

import argparse
import asyncio
import json
import math
import signal
import time
import uuid

import websockets


def _create(origin: str, obj: str) -> dict:
    return {
        "kind": "create",
        "object": obj,
        "lamport": 1,
        "origin": origin,
        "name": f"Load-{obj[:8]}",
        "object_type": "MESH",
        "collection": "Scene Collection",
        "transform": {
            "location": [0.0, 0.0, 0.0],
            "rotation": {"mode": "XYZ", "values": [0.0, 0.0, 0.0]},
            "scale": [1.0, 1.0, 1.0],
        },
        "mesh": {"vertices": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], "faces": [[0, 1, 2]]},
    }


async def _discard(ws) -> None:
    """Read everything relayed to us, as a real client does; otherwise the server backs up."""
    async for _ in ws:
        pass


async def _client(uri: str, rate: float, stop: asyncio.Event, sent: list[int], index: int) -> None:
    origin, obj = str(uuid.uuid4()), str(uuid.uuid4())
    async with websockets.connect(uri) as ws:
        reader = asyncio.create_task(_discard(ws))
        await ws.send(json.dumps({"v": 1, "type": "ops", "ops": [_create(origin, obj)]}))
        lamport = 1
        next_send = time.monotonic() + index / (rate * 8)  # don't all send in the same instant
        while not stop.is_set():
            await asyncio.sleep(max(0, next_send - time.monotonic()))
            next_send += 1 / rate
            lamport += 1
            angle = lamport / 20
            op = {
                "kind": "set",
                "object": obj,
                "property": "location",
                "value": [math.cos(angle), math.sin(angle), 0.0],
                "lamport": lamport,
                "origin": origin,
            }
            await ws.send(json.dumps({"v": 1, "type": "ops", "ops": [op]}))
            sent[index] += 1
        reader.cancel()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("room_id")
    parser.add_argument("--url", default="ws://localhost:8000")
    parser.add_argument("--clients", type=int, default=4)
    parser.add_argument("--rate", type=float, default=20, help="messages/s per client (detect's limit)")
    args = parser.parse_args()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    sent = [0] * args.clients
    started = time.monotonic()
    uri = f"{args.url}/ws/rooms/{args.room_id}"
    await asyncio.gather(*(_client(uri, args.rate, stop, sent, i) for i in range(args.clients)))
    elapsed = time.monotonic() - started
    print(f"{args.clients} clients sent {sum(sent)} messages in {elapsed:.1f} s: {sum(sent) / elapsed:.0f}/s")


if __name__ == "__main__":
    asyncio.run(main())
