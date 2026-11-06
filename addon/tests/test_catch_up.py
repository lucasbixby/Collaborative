"""Tests for joining a room that already has state (#20): catch-up, `synced`, merge on join.

A fake relay stands in for the server: the test plays the server's part by sending the
catch-up messages and `synced` itself, then calls `client.drain()` as Blender's timer would.
Imports happen inside each test for the reason given in test_join_leave.py.
"""

import json

import bpy
from conftest import wait_until

ROOM_ORIGIN = "22222222-2222-4222-8222-222222222222"
ROOM_CUBE = "aaaaaaaa-0000-4000-8000-000000000001"
ROOM_PLANE = "aaaaaaaa-0000-4000-8000-000000000002"
GONE = "aaaaaaaa-0000-4000-8000-000000000003"


def _create(collab_id, name, lamport, location=(0.0, 0.0, 0.0)):
    return {
        "kind": "create",
        "object": collab_id,
        "lamport": lamport,
        "origin": ROOM_ORIGIN,
        "name": name,
        "object_type": "MESH",
        "collection": "Scene Collection",
        "transform": {
            "location": list(location),
            "rotation": {"mode": "XYZ", "values": [0.0, 0.0, 0.0]},
            "scale": [1.0, 1.0, 1.0],
        },
        "mesh": {
            "vertices": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            "faces": [[0, 1, 2]],
        },
    }


def _set(collab_id, value, lamport):
    return {"kind": "set", "object": collab_id, "property": "location", "value": list(value),
            "lamport": lamport, "origin": ROOM_ORIGIN}


def _delete(collab_id, lamport):
    return {"kind": "delete", "object": collab_id, "lamport": lamport, "origin": ROOM_ORIGIN}


def _ops(*ops):
    return json.dumps({"v": 1, "type": "ops", "ops": list(ops)})


def _synced(seq=10):
    return json.dumps({"v": 1, "type": "synced", "seq": seq})


def _local_cube(name="Local"):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _join(addon, relay):
    bpy.context.window_manager.room_id = "room-a"
    prefs = bpy.context.preferences.addons["collaborative_blender"].preferences
    prefs.server_url = f"ws://localhost:{relay.port}"
    assert bpy.ops.collaborative.join_room() == {"FINISHED"}
    wait_until(lambda: addon.client.status() == "connected" and relay._sockets)


def _serve(addon, relay, *messages):
    """Send `messages` as the server would, and apply them as Blender's drain tick would."""
    count = addon.client._conn.inbox.qsize()
    for text in messages:
        relay.send_to_client(text)
    wait_until(lambda: addon.client._conn.inbox.qsize() >= count + len(messages))
    addon.client.drain()


def _barrier(addon, relay):
    """Wait until everything the client queued so far has reached the relay: the outbox is
    first in, first out, so once this marker arrives, nothing queued before it is pending."""
    addon.client.send({"type": "barrier"})
    wait_until(lambda: relay.received and json.loads(relay.received[-1]).get("type") == "barrier")
    relay.received.pop()


def _sent(relay):
    return [json.loads(text) for text in relay.received]


def _sent_creates(relay):
    return [op for m in _sent(relay) for op in m["ops"] if op["kind"] == "create"]


def test_catch_up_builds_the_room_in_an_empty_scene_and_echoes_nothing(addon, relay):
    _join(addon, relay)
    assert not addon.client.synced()

    _serve(
        addon,
        relay,
        _ops(_create(ROOM_CUBE, "Cube", 1)),
        _ops(_create(ROOM_PLANE, "Plane", 2)),
        _ops(_set(ROOM_CUBE, (3.0, 0.0, 0.0), 5)),
        _ops(_delete(GONE, 4)),
        _synced(),
    )

    cube = addon.ids.find_object(ROOM_CUBE)
    assert cube is not None and addon.ids.find_object(ROOM_PLANE) is not None
    assert tuple(cube.location) == (3.0, 0.0, 0.0)
    assert GONE in addon.ordering.tombstones
    assert addon.client.synced()
    assert addon.client._conn.synced_seq == 10
    # Applied objects are in detect's cache, so nothing goes back out as a local edit.
    addon.detect._dirty = True
    assert addon.detect.flush() is None
    assert _sent(relay) == []


def test_synced_offers_only_local_meshes_the_room_does_not_know(addon, relay):
    known = _local_cube("Known")
    unknown = _local_cube("Unknown")
    light = bpy.data.objects.new("Lamp", bpy.data.lights.new("Lamp", "POINT"))
    bpy.context.scene.collection.objects.link(light)
    addon.ids.ensure_ids()
    _join(addon, relay)

    _serve(addon, relay, _ops(_set(addon.ids.get_id(known), (1.0, 0.0, 0.0), 3)), _synced())
    _barrier(addon, relay)
    creates = _sent_creates(relay)
    assert [op["object"] for op in creates] == [addon.ids.get_id(unknown)]
    assert creates[0]["name"] == "Unknown"
    assert creates[0]["lamport"] > 3  # after everything the catch-up showed it
    assert all(len(m["ops"]) == 1 for m in _sent(relay))  # one create per message
    # The known object took the room's value; the light stays local.
    assert tuple(known.location) == (1.0, 0.0, 0.0)
    addon.detect._dirty = True
    addon.detect.flush()
    _barrier(addon, relay)
    assert len(_sent_creates(relay)) == 1  # not sent again by the next flush


def test_a_catch_up_delete_removes_a_stale_local_object(addon, relay):
    stale = _local_cube("Stale")
    addon.ids.ensure_ids()
    stale_id = addon.ids.get_id(stale)
    _join(addon, relay)

    _serve(addon, relay, _ops(_delete(stale_id, 7)), _synced())
    _barrier(addon, relay)

    assert addon.ids.find_object(stale_id) is None
    assert stale_id in addon.ordering.tombstones
    assert _sent_creates(relay) == []


def test_a_local_object_with_a_tombstoned_id_is_not_offered(addon, relay):
    # Cmd+Z can bring back a deleted object with its old ID before detect's next flush gives
    # it a new one; offering it under the old ID would resurrect it on clients that never
    # saw the delete.
    restored = _local_cube("Restored")
    addon.ids.ensure_ids()
    addon.ordering.tombstones.add(addon.ids.get_id(restored))
    _join(addon, relay)

    _serve(addon, relay, _synced(0))
    _barrier(addon, relay)

    assert _sent_creates(relay) == []


def test_an_empty_room_gets_every_local_mesh(addon, relay):
    first, second = _local_cube("First"), _local_cube("Second")
    addon.ids.ensure_ids()
    _join(addon, relay)

    _serve(addon, relay, _synced(0))

    wait_until(lambda: len(relay.received) >= 2)
    assert sorted(op["object"] for op in _sent_creates(relay)) == sorted(
        [addon.ids.get_id(first), addon.ids.get_id(second)]
    )


def test_a_reconnect_within_one_join_does_not_resend_creates(addon, relay):
    _local_cube("Mine")
    addon.ids.ensure_ids()
    _join(addon, relay)
    _serve(addon, relay, _synced(0))
    wait_until(lambda: len(_sent_creates(relay)) == 1)

    relay.drop_clients()
    wait_until(lambda: addon.client._conn.generation == 2 and relay._sockets, timeout=5)
    assert not addon.client.synced()  # the new socket hasn't had its catch-up yet

    _serve(addon, relay, _ops(_create(ROOM_CUBE, "Cube", 1)), _synced(1))
    _barrier(addon, relay)

    assert addon.client.synced()
    assert addon.ids.find_object(ROOM_CUBE) is not None  # catch-up still applies
    assert len(_sent_creates(relay)) == 1


def test_a_synced_from_a_dead_socket_is_ignored(addon, relay):
    _join(addon, relay)
    conn = addon.client._conn

    addon.client._handle_message(conn, conn.generation - 1, _synced(3))

    assert not addon.client.synced()
    assert conn.synced_seq is None
    assert not conn.joined


def test_leaving_and_joining_again_offers_new_local_objects(addon, relay):
    _join(addon, relay)
    _serve(addon, relay, _synced(0))
    bpy.ops.collaborative.leave_room()

    added = _local_cube("Added while away")
    addon.ids.ensure_ids()
    _join(addon, relay)
    _serve(addon, relay, _synced(0))

    wait_until(lambda: len(relay.received) >= 1)
    assert [op["object"] for op in _sent_creates(relay)] == [addon.ids.get_id(added)]
