#!/usr/bin/env python3
"""The far end of a round-trip measurement across two machines (#24). Needs only `websockets`.

Answers every `set location` with its own, for the same object and value at the next Lamport time,
so scripts/latency_report.py --rtt can pair them from the Blender side's file alone. Clocks on two
machines don't agree, so this records no times at all.

    pip install websockets
    python3 latency_probe.py latency --url ws://<server-ip>:8000 --token <token>

The token (or COLLAB_TOKEN) is a member's: latency_run.py prints one for its room.
"""

import argparse
import asyncio
import json
import os
import sys
import uuid

import websockets
from websockets.exceptions import ConnectionClosed


def reply_to(message: dict, origin: str) -> dict | None:
    """The reply to one relayed `ops` message, or None if there's nothing in it to answer."""
    if message.get("type") != "ops":
        return None
    replies = [
        {**op, "lamport": op["lamport"] + 1, "origin": origin}
        for op in message["ops"]
        if op["kind"] == "set" and op["property"] == "location"
    ]
    return {"v": 1, "type": "ops", "ops": replies} if replies else None


def auth_headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


async def answer(uri: str, token: str | None) -> None:
    origin = str(uuid.uuid4())
    async with websockets.connect(uri, additional_headers=auth_headers(token)) as ws:
        print(f"Connected to {uri}. Answering moves; Ctrl+C to stop.", flush=True)
        answered = 0
        async for raw in ws:
            reply = reply_to(json.loads(raw), origin)
            if reply is not None:
                await ws.send(json.dumps(reply))
                answered += 1
                if answered % 25 == 0:
                    print(f"answered {answered}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("room_id")
    parser.add_argument("--url", default="ws://localhost:8000")
    parser.add_argument("--token", default=os.environ.get("COLLAB_TOKEN"), help="or COLLAB_TOKEN")
    args = parser.parse_args()

    uri = f"{args.url}/ws/rooms/{args.room_id}"
    try:
        asyncio.run(answer(uri, args.token))
    except KeyboardInterrupt:
        pass
    except ConnectionClosed as exc:
        print(f"The server closed the connection: {exc}")
        if exc.rcvd is not None and exc.rcvd.code in (4401, 4403):
            print("Pass a room member's token with --token (latency_run.py prints one).")
            return 1
    except OSError as exc:
        print(f"Couldn't connect to {uri}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
