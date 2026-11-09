#!/usr/bin/env python3
"""Run one latency scenario (#24) with real Blender windows, and leave the timing files in a folder.

    scripts/latency_run.py idle                 single nudges, A → B
    scripts/latency_run.py drag                 three simulated grabs of about 10 s
    scripts/latency_run.py drag --manual        same, but you drag by hand and press Enter
    scripts/latency_run.py create               a mesh just under 64 KiB, repeatedly
    scripts/latency_run.py load --clients 8     nudges while simulated clients send
    scripts/latency_run.py rtt --host 0.0.0.0   nudges with no B: latency_probe.py answers them
    scripts/latency_run.py idle --url ws://localhost:8000 --name docker   against a server you run

Starts its own server with a temporary database (port 8000 must be free), unless --url is given.
Either way it registers a throwaway user and creates --room as them (#16, #18), so against a
server you run, pick a room that doesn't exist yet.
Blender uses throwaway settings, so yours aren't touched. Then read the results with
scripts/latency_report.py latency-results/<name>. Needs server/.venv.
"""

import argparse
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import latency_report

REPO = Path(__file__).resolve().parents[1]
SERVER_PYTHON = REPO / "server" / ".venv" / "bin" / "python"
BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
HEALTH_URL = "http://127.0.0.1:8000/health"
DRIVER_SCENARIO = {"idle": "nudge", "drag": "drag", "create": "create", "load": "nudge", "rtt": "nudge"}
LOAD_SETTLE_S = 3


def wait_for(test, timeout: float, what: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if test():
            return
        time.sleep(0.1)
    raise SystemExit(f"Timed out waiting for {what}")


def http_url(ws_url: str) -> str:
    """The REST side of a ws:// or wss:// server URL."""
    return "http" + ws_url.removeprefix("ws") if ws_url.startswith("ws") else ws_url


def post(url: str, body: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def sign_up(server: str, room: str) -> str:
    """Register a throwaway user, make the room as them (#18), and return their token."""
    credentials = {"username": f"latency-{secrets.token_hex(4)}", "password": secrets.token_urlsafe(16)}
    post(f"{server}/api/auth/register", credentials)
    token = post(f"{server}/api/auth/login", credentials)["token"]
    try:
        post(f"{server}/api/rooms", {"room_id": room}, token)
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            raise SystemExit(f"Room {room!r} already exists on {server}; pass another --room.") from None
        raise
    return token


def server_is_up() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=1):
            return True
    except OSError:
        return False


def start_server(out: Path, scratch: Path, host: str) -> subprocess.Popen:
    if server_is_up():
        raise SystemExit("Something is already on port 8000. Stop it, or pass --url to use it.")
    env = {
        **os.environ,
        "COLLAB_TIMING": str(out / "server.jsonl"),
        "COLLAB_DATABASE_URL": f"sqlite+aiosqlite:///{scratch}/latency.db",
    }
    process = subprocess.Popen(
        [str(SERVER_PYTHON), "-m", "uvicorn", "app.main:app", "--host", host, "--log-level", "warning"],
        cwd=REPO / "server",
        env=env,
        stdout=(out / "server.log").open("w"),
        stderr=subprocess.STDOUT,
    )
    wait_for(server_is_up, 15, "the server")
    return process


def start_blender(client: str, out: Path, scratch: Path, sync: Path, args, x: int) -> subprocess.Popen:
    config = scratch / client
    addons = config / "scripts" / "addons"
    addons.mkdir(parents=True)
    (config / "config").mkdir()
    (addons / "collaborative_blender").symlink_to(REPO / "addon" / "collaborative_blender")
    env = {
        **os.environ,
        "COLLAB_CLIENT": client,
        "TMPDIR": str(config),  # Blender saves quit.blend here; leave your Recover Last Session alone
        "COLLAB_TIMING": str(out / f"{client}.jsonl"),
        "BLENDER_USER_SCRIPTS": str(config / "scripts"),
        "BLENDER_USER_CONFIG": str(config / "config"),
        "LATENCY_SCENARIO": "manual" if args.manual else DRIVER_SCENARIO[args.scenario],
        "LATENCY_SAMPLES": str(args.samples),
        "LATENCY_OBJECTS": str(args.objects),
        "LATENCY_PEER": "0" if args.scenario == "rtt" else "1",
        "LATENCY_SYNC_DIR": str(sync),
        "LATENCY_ROOM": args.room,
        "LATENCY_URL": args.url or "ws://localhost:8000",
        "LATENCY_TOKEN": args.token,
    }
    command = [BLENDER, "--factory-startup", "--window-geometry", str(x), "0", "800", "600"]
    if not args.manual:
        command.append("--enable-event-simulate")  # also keeps stray real input out of the run
    command += ["--python", str(REPO / "scripts" / "latency_blender.py")]
    log = (out / f"{client}.log").open("w")
    return subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("scenario", choices=sorted(DRIVER_SCENARIO))
    parser.add_argument("--name", help="results folder name (default: the scenario)")
    parser.add_argument("--samples", type=int, default=220, help="nudges or creates (default 220)")
    parser.add_argument("--clients", type=int, default=4, help="simulated clients for load")
    parser.add_argument("--objects", type=int, default=0, help="extra objects in each scene")
    parser.add_argument("--manual", action="store_true", help="you make the edits by hand in A")
    parser.add_argument("--url", help="use the server already running at this ws:// URL")
    parser.add_argument("--host", default="127.0.0.1", help="address our server listens on")
    parser.add_argument("--room", default="latency")
    args = parser.parse_args()

    out = REPO / "latency-results" / (args.name or args.scenario)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    scratch = Path(tempfile.mkdtemp(prefix="collab-latency-"))
    sync = scratch / "sync"
    sync.mkdir()

    server = None if args.url else start_server(out, scratch, args.host)
    url = args.url or "ws://localhost:8000"
    clients = ["A"] if args.scenario == "rtt" else ["B", "A"]
    blenders = {}
    load = None
    try:
        args.token = sign_up(http_url(url), args.room)
        for index, client in enumerate(clients):
            blenders[client] = start_blender(client, out, scratch, sync, args, 820 * (client == "B"))
        wait_for(lambda: (sync / "ready").exists(), 60, "the Blenders to get ready")

        if args.scenario == "load":
            load = subprocess.Popen(
                [str(SERVER_PYTHON), str(REPO / "scripts" / "latency_load.py"), args.room,
                 "--url", url, "--clients", str(args.clients), "--token", args.token],
                stdout=(out / "load.log").open("w"),
                stderr=subprocess.STDOUT,
            )
            time.sleep(LOAD_SETTLE_S)
        if args.scenario == "rtt":
            print(f"On the other machine: latency_probe.py {args.room} --url ws://<this-ip>:8000 "
                  f"--token {args.token}")
            input("Start latency_probe.py there, then press Enter: ")
        (sync / "start").write_text("x")
        if args.manual:
            input("Drag the cube in A (for about 10 s), then press Enter: ")
            (sync / "stop").write_text("x")

        for client, process in blenders.items():
            process.wait(timeout=600)
    finally:
        if load is not None:
            load.send_signal(signal.SIGTERM)
            load.wait(timeout=10)
        for process in blenders.values():
            if process.poll() is None:
                process.terminate()
        if server is not None:
            server.send_signal(signal.SIGTERM)
            server.wait(timeout=10)
    for meta in sync.glob("meta_*.json"):
        shutil.copy(meta, out)

    failed = False
    if args.scenario == "rtt":
        count = len(latency_report.round_trips(latency_report.load(out)))
    else:
        count = len(latency_report.samples(latency_report.load(out))[0])
    print(f"{count} samples")
    if count == 0:
        print("FAILED: nothing was measured")
        failed = True
    for client in clients:
        result = sync / f"result_{client}.json"
        ok = result.exists() and '"ok": true' in result.read_text()
        print(f"client {client}: {'ok' if ok else 'FAILED, see ' + str(out / (client + '.log'))}")
        failed |= not ok
    shutil.rmtree(scratch, ignore_errors=True)
    print(f"Results in {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
