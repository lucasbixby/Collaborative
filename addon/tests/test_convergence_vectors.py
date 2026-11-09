"""The real add-on agrees with the convergence model (#21).

tests/vectors/convergence.json (written by server/tests/sync/test_convergence.py) holds short
scenarios: one client's delivery stream and the scene the reference model ends with. Each is fed
through the real `apply.apply_message` in headless Blender, starting from an empty scene and the
add-on's fresh ordering state (the `addon` fixture re-imports it), and the real objects are
compared with the expected scene. A mismatch is a bug in the add-on or the model, not in this test.

A scenario with `known_divergence` is one the add-on is known to get wrong; it's a strict xfail,
so it fails loudly once fixed and the mark can go.
"""

import json
from pathlib import Path

import bpy
import pytest

VECTORS = Path(__file__).resolve().parents[2] / "tests" / "vectors" / "convergence.json"
SCENARIOS = json.loads(VECTORS.read_text())["scenarios"]
TOLERANCE = 1e-5


def _rotation(obj) -> dict:
    mode = obj.rotation_mode
    if mode == "QUATERNION":
        values = obj.rotation_quaternion
    elif mode == "AXIS_ANGLE":
        values = obj.rotation_axis_angle
    else:
        values = obj.rotation_euler
    return {"mode": mode, "values": list(values)}


def _scene(addon) -> dict[str, dict]:
    scene = {}
    for obj in bpy.context.scene.objects:
        collab_id = addon.ids.get_id(obj)
        if collab_id is not None:
            scene[collab_id] = {
                "name": obj.name,
                "location": list(obj.location),
                "rotation": _rotation(obj),
                "scale": list(obj.scale),
            }
    return scene


def _close(actual, expected) -> bool:
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _close(actual[key], expected[key]) for key in expected
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(map(_close, actual, expected))
    if isinstance(expected, float):
        return abs(actual - expected) <= TOLERANCE
    return actual == expected


def test_there_are_vectors():
    assert len(SCENARIOS) >= 15


def _param(scenario):
    marks = []
    if "known_divergence" in scenario:
        marks.append(pytest.mark.xfail(strict=True, reason=scenario["known_divergence"]))
    return pytest.param(scenario, id=scenario["name"], marks=marks)


@pytest.mark.parametrize("scenario", [_param(s) for s in SCENARIOS])
def test_apply_message_reaches_the_expected_scene(addon, scenario):
    assert not bpy.context.scene.objects  # the `scene` fixture's empty factory scene
    for message in scenario["messages"]:
        addon.apply.apply_message(message)

    actual = _scene(addon)
    assert _close(actual, scenario["expected"]), (
        f"{scenario['name']} ({scenario['covers']}):\n  real   {actual}\n"
        f"  model  {scenario['expected']}"
    )


@pytest.mark.xfail(strict=True, reason="Blender's unique names make a same-name rename order-dependent")
def test_two_clients_renaming_two_objects_to_one_name_converge(addon):
    # Client A renames X to "Shared" and then hears Y's rename; client B the other way round.
    # Each ends with a different object called "Shared.001", and nothing sends a correction.
    scenario = next(s for s in SCENARIOS if s["name"] == "same_name_on_two_objects")
    creates = scenario["messages"][:2]
    x, y = (message["ops"][0]["object"] for message in creates)
    origin_a, origin_b = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

    def names_after(first: str, second: str) -> dict[str, str]:
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj)
        addon.ordering.versions = addon.ordering.Versions()  # a fresh client each time
        addon.ordering.tombstones.clear()
        for message in creates:
            addon.apply.apply_message(message)
        for lamport, (obj, origin) in enumerate([(first, origin_a), (second, origin_b)], start=5):
            op = {"kind": "set", "object": obj, "property": "name", "value": "Shared",
                  "lamport": lamport, "origin": origin}
            addon.apply.apply_message({"v": 1, "type": "ops", "ops": [op]})
        return {collab_id: values["name"] for collab_id, values in _scene(addon).items()}

    assert names_after(x, y) == names_after(y, x)
