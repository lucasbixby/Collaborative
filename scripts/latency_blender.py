"""Runs inside Blender, started by latency_run.py (#24): drives one client through a scenario.

Client A makes the edits; B only receives. Everything goes through real Blender operators and the
real add-on, on Blender's own timers. Files in LATENCY_SYNC_DIR keep the processes in step.
"""

import json
import math
import os
import pathlib
import random
import time
import traceback

import addon_utils
import bpy

ME = os.environ["COLLAB_CLIENT"]
SCENARIO = os.environ["LATENCY_SCENARIO"]  # nudge, drag, create or manual
SAMPLES = int(os.environ["LATENCY_SAMPLES"])
EXTRA_OBJECTS = int(os.environ.get("LATENCY_OBJECTS", "0"))
HAS_PEER = os.environ.get("LATENCY_PEER", "1") == "1"
SYNC = pathlib.Path(os.environ["LATENCY_SYNC_DIR"])
TIMEOUT_S = float(os.environ.get("LATENCY_TIMEOUT", "300"))
PROBE_NAME = "LatencyProbe"
MAX_MESSAGE_BYTES = 64 * 1024

started = time.time()
draws: list[int] = []


def mark(name: str) -> None:
    (SYNC / name).write_text("x")


def seen(name: str) -> bool:
    return (SYNC / name).exists()


def say(*parts) -> None:
    print(f"[latency {ME} {time.time() - started:6.1f}]", *parts, flush=True)


def view3d() -> dict:
    window = bpy.context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    return {"window": window, "area": area, "region": region}


def client():
    from collaborative_blender import client as module

    return module


def timing():
    from collaborative_blender import timing as module

    return module


def probe():
    return bpy.data.objects.get(PROBE_NAME)


def finish(ok: bool, why: str = "") -> None:
    say("finished" if ok else f"FAILED: {why}")
    (SYNC / f"result_{ME}.json").write_text(json.dumps({"ok": ok, "why": why}))
    try:
        client().disconnect()
        with open(os.environ["COLLAB_TIMING"], "a", encoding="utf-8") as file:
            file.writelines(json.dumps({"stage": "draw", "source": ME, "mono_ns": mono_ns}) + "\n" for mono_ns in draws)
        timing().configure(None)
    finally:
        bpy.ops.wm.quit_blender()


def guarded(function):
    """A timer callback that ends the run on an exception or the time limit."""

    def wrapper():
        try:
            if time.time() - started > TIMEOUT_S:
                finish(False, f"timed out; status {client().status()}")
                return None
            return function()
        except Exception:  # noqa: BLE001 - any failure ends the run and is reported
            finish(False, traceback.format_exc())
            return None

    return wrapper


def poll_until(test, then) -> None:
    def check():
        if test():
            then()
            return None
        return 0.05

    bpy.app.timers.register(guarded(check))


def finish_after_settling() -> None:
    mark(f"{ME}_edits_done")
    bpy.app.timers.register(guarded(lambda: finish(True)), first_interval=3.0)


# -- Client A's edits -----------------------------------------------------------------------------


def nudge_scenario() -> None:
    """One small move at a time, at intervals that can't lock to the 50 ms detect tick."""
    state = {"left": SAMPLES}

    def step():
        if state["left"] == 0:
            finish_after_settling()
            return None
        state["left"] -= 1
        obj = probe()
        with bpy.context.temp_override(**view3d()):
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.transform.translate(value=(random.uniform(-0.1, 0.1), 0.01, 0))
        return random.uniform(0.25, 0.40)

    bpy.app.timers.register(guarded(step))


def drag_scenario() -> None:
    """A real modal grab moved by simulated mouse events: three grabs of about 10 s each.

    Invoked directly, the way the G key's keymap entry does, because a simulated key press doesn't
    reach the keymap. From there on it's Blender's own transform modal handling each mouse move.
    """
    window = bpy.context.window_manager.windows[0]
    region = view3d()["region"]
    x, y = region.x + region.width // 2, region.y + region.height // 2
    state = {"grab": 0, "started": None}

    def begin_grab():
        obj = probe()
        with bpy.context.temp_override(**view3d()):
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.transform.translate("INVOKE_DEFAULT")
        if not window.modal_operators:
            raise RuntimeError("the grab didn't start: no modal operator is running")
        state["started"] = time.time()

    def step():
        if state["started"] is None:
            begin_grab()
            return 0.1
        elapsed = time.time() - state["started"]
        if elapsed < 10:
            angle, radius = elapsed * 3, 150 + 80 * math.sin(elapsed * 1.7)
            window.event_simulate(
                type="MOUSEMOVE",
                value="NOTHING",
                x=x + int(radius * math.cos(angle)),
                y=y + int(radius * math.sin(angle)),
            )
            return 1 / 60
        window.event_simulate(type="LEFTMOUSE", value="PRESS", x=x, y=y)
        window.event_simulate(type="LEFTMOUSE", value="RELEASE", x=x, y=y)
        state["started"] = None
        state["grab"] += 1
        if state["grab"] == 3:
            finish_after_settling()
            return None
        return 1.0

    bpy.app.timers.register(guarded(step))


def _grid_message_bytes(obj) -> int:
    """About what detect.py will send for this mesh: same rounding, plus the op's other fields."""
    mesh = {
        "vertices": [[round(c, 6) for c in v.co] for v in obj.data.vertices],
        "faces": [list(p.vertices) for p in obj.data.polygons],
    }
    return len(json.dumps(mesh)) + 450


def _largest_grid_subdivisions() -> int:
    """The largest real grid primitive that still fits the message limit."""
    best = 2
    for subdivisions in range(10, 100):
        with bpy.context.temp_override(**view3d()):
            bpy.ops.mesh.primitive_grid_add(x_subdivisions=subdivisions, y_subdivisions=subdivisions)
        obj = bpy.context.active_object
        size = _grid_message_bytes(obj)
        bpy.data.objects.remove(obj, do_unlink=True)
        if size >= MAX_MESSAGE_BYTES - 500:
            break
        best, best_size = subdivisions, size
    say(f"largest grid: {best} subdivisions, about {best_size} bytes")
    (SYNC / "meta_create.json").write_text(json.dumps({"subdivisions": best, "bytes": best_size}))
    return best


def create_scenario() -> None:
    """A mesh just under the size limit, added with the real operator and then deleted."""
    subdivisions = _largest_grid_subdivisions()
    state = {"left": SAMPLES, "last": None}

    def step():
        with bpy.context.temp_override(**view3d()):
            if state["last"] is not None:
                bpy.ops.object.select_all(action="DESELECT")
                state["last"].select_set(True)
                bpy.ops.object.delete()
                state["last"] = None
                if state["left"] == 0:
                    finish_after_settling()
                    return None
                return random.uniform(0.7, 0.9)
            bpy.ops.mesh.primitive_grid_add(x_subdivisions=subdivisions, y_subdivisions=subdivisions)
            state["last"] = bpy.context.active_object
            state["left"] -= 1
        return random.uniform(0.7, 0.9)

    bpy.app.timers.register(guarded(step))


SCENARIOS = {"nudge": nudge_scenario, "drag": drag_scenario, "create": create_scenario}


def run_scenario() -> None:
    mark("ready")
    if SCENARIO == "manual":
        say("ready: drag the cube by hand, then press Enter in the terminal")
        poll_until(lambda: seen("stop"), finish_after_settling)
        return

    def go():
        SCENARIOS[SCENARIO]()

    poll_until(lambda: seen("start"), go)


# -- Setup ----------------------------------------------------------------------------------------


def add_probe() -> None:
    with bpy.context.temp_override(**view3d()):
        bpy.ops.mesh.primitive_cube_add(size=1)
    bpy.context.active_object.name = PROBE_NAME


def run_a() -> None:
    def peer_ready():
        add_probe()
        if HAS_PEER:
            poll_until(lambda: seen("B_has_probe"), run_scenario)
        else:
            bpy.app.timers.register(guarded(lambda: run_scenario()), first_interval=1.0)

    poll_until(lambda: not HAS_PEER or seen("B_joined"), peer_ready)


def run_b() -> None:
    mark("B_joined")

    def has_probe():
        mark("B_has_probe")
        poll_until(lambda: seen("A_edits_done"), finish_after_settling)

    poll_until(lambda: probe() is not None, has_probe)


def _on_draw() -> None:
    draws.append(time.perf_counter_ns())


def begin():
    try:
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj)
        for index in range(EXTRA_OBJECTS):
            mesh = bpy.data.meshes.new(f"Extra{index}")
            bpy.context.scene.collection.objects.link(bpy.data.objects.new(mesh.name, mesh))
        addon_utils.enable("collaborative_blender", default_set=True)
        bpy.types.SpaceView3D.draw_handler_add(_on_draw, (), "WINDOW", "POST_PIXEL")
        bpy.context.window_manager.room_id = os.environ.get("LATENCY_ROOM", "latency")
        prefs = bpy.context.preferences.addons["collaborative_blender"].preferences
        prefs.server_url = os.environ.get("LATENCY_URL", "ws://localhost:8000")
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
            bpy.ops.collaborative.join_room()
        say(f"Blender {bpy.app.version_string}, {SCENARIO}, joined {prefs.server_url}")
        poll_until(lambda: client().status() == "connected", run_a if ME == "A" else run_b)
    except Exception:  # noqa: BLE001 - any failure ends the run and is reported
        finish(False, traceback.format_exc())


bpy.app.timers.register(begin, first_interval=2.0)
