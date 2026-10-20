#!/usr/bin/env python3
"""Dev aid: talk to the WebSocket relay (#11) by hand, without running Blender.

Connects to one room, then on every Enter key press sends the next example `ops`
message from docs/protocol.md (cycling through them), and prints everything it
receives. Run two of these in the same room to watch messages relayed between them,
and a third in a different room to see it get nothing.

Usage (from server/, with the server already running — see README):
    python3 scripts/ws_probe.py <room_id> [--url ws://localhost:8000]
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import websockets

PROTOCOL_MD = Path(__file__).resolve().parents[2] / "docs" / "protocol.md"


def _example_messages() -> list[dict]:
    """The example `ops` messages in docs/protocol.md, in the order they appear."""
    text = PROTOCOL_MD.read_text(encoding="utf-8")
    blocks = [json.loads(block) for block in re.findall(r"```json\n(.*?)```", text, re.DOTALL)]
    messages = [block for block in blocks if block.get("type") == "ops"]
    if not messages:
        sys.exit(f"No example `ops` messages found in {PROTOCOL_MD}")
    return messages


async def _receive(ws) -> None:
    async for raw in ws:
        print(f"<< {raw}")


async def _send_on_enter(ws, messages: list[dict]) -> None:
    loop = asyncio.get_running_loop()
    index = 0
    while True:
        await loop.run_in_executor(None, input)
        kinds = "+".join(op["kind"] for op in messages[index % len(messages)]["ops"])
        text = json.dumps(messages[index % len(messages)])
        await ws.send(text)
        print(f">> ({kinds}) {text}")
        index += 1


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("room_id", help="Must match ^[A-Za-z0-9_-]{1,64}$")
    parser.add_argument("--url", default="ws://localhost:8000", help="Server base URL")
    args = parser.parse_args()

    messages = _example_messages()
    uri = f"{args.url}/ws/rooms/{args.room_id}"
    print(f"Connecting to {uri}")
    print("Press Enter to send the next example message, Ctrl+C to quit.")

    try:
        async with websockets.connect(uri) as ws:
            await asyncio.gather(_receive(ws), _send_on_enter(ws, messages))
    except websockets.exceptions.ConnectionClosed as exc:
        print(f"Connection closed: {exc}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        print()
