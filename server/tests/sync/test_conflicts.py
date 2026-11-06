"""Tests for `RoomState` (#20): folding operations with the clients' rules (protocol rules 1–3)."""

import json
import random

import pytest

from app.sync.conflicts import RoomState

A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
X = "11111111-1111-4111-8111-111111111111"
Y = "22222222-2222-4222-8222-222222222222"


def create(obj=X, lamport=1, origin=A, name="Cube"):
    return {
        "kind": "create",
        "object": obj,
        "lamport": lamport,
        "origin": origin,
        "name": name,
        "object_type": "MESH",
        "collection": "Collection",
        "transform": {
            "location": [0.0, 0.0, 0.0],
            "rotation": {"mode": "XYZ", "values": [0.0, 0.0, 0.0]},
            "scale": [1.0, 1.0, 1.0],
        },
        "mesh": {
            "vertices": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            "faces": [[0, 1, 2]],
        },
    }


def move(x, obj=X, lamport=2, origin=A, prop="location"):
    return {
        "kind": "set",
        "object": obj,
        "property": prop,
        "value": [x, 0.0, 0.0],
        "lamport": lamport,
        "origin": origin,
    }


def delete(obj=X, lamport=3, origin=A):
    return {"kind": "delete", "object": obj, "lamport": lamport, "origin": origin}


def fold(*ops):
    return RoomState().apply_all(ops)


# -- set ----------------------------------------------------------------------------------


def test_the_highest_lamport_wins_per_key_whatever_the_order():
    late, early = move(5.0, lamport=9), move(1.0, lamport=4)

    assert fold(create(), late, early).to_ops() == [create(), late]
    assert fold(create(), early, late).to_ops() == [create(), late]


def test_a_lamport_tie_goes_to_the_larger_origin():
    from_a, from_b = move(1.0, lamport=5, origin=A), move(2.0, lamport=5, origin=B)

    assert fold(create(), from_b, from_a).to_ops()[1:] == [from_b]
    assert fold(create(), from_a, from_b).to_ops()[1:] == [from_b]


def test_different_properties_of_one_object_both_keep_their_value():
    location, scale = move(1.0, lamport=5), move(2.0, lamport=4, origin=B, prop="scale")

    assert fold(create(), location, scale).to_ops() == [create(), location, scale]


def test_an_identical_set_replayed_changes_nothing():
    op = move(1.0, lamport=5)

    assert fold(create(), op, op) == fold(create(), op)


def test_a_set_older_than_its_create_loses_whichever_arrives_first():
    stale = move(9.0, lamport=1)
    newer_create = create(lamport=4)

    assert fold(stale, newer_create).to_ops() == [newer_create]
    assert fold(newer_create, stale).to_ops() == [newer_create]


def test_a_set_newer_than_its_create_survives_arriving_first():
    op = move(9.0, lamport=7)

    assert fold(op, create(lamport=4)).to_ops() == [create(lamport=4), op]


def test_a_set_for_an_object_the_log_never_created_is_kept():
    # Logs from before #20 (shared .blend files) have these; a receiver without the object
    # drops it (protocol rule 9), one that has it applies it.
    op = move(1.0, obj=Y)

    assert fold(op).to_ops() == [op]


# -- delete -------------------------------------------------------------------------------


def test_delete_drops_the_create_and_sets_and_keeps_a_tombstone():
    gone = delete(lamport=3)

    assert fold(create(), move(1.0), gone).to_ops() == [gone]


def test_a_set_after_delete_is_ignored_even_with_a_higher_lamport():
    gone = delete(lamport=3)

    assert fold(create(), gone, move(1.0, lamport=99, origin=B)).to_ops() == [gone]


def test_a_create_after_delete_is_ignored():
    gone = delete(lamport=3)

    assert fold(create(), gone, create(lamport=50)).to_ops() == [gone]


def test_a_delete_before_its_create_wins():
    gone = delete(lamport=1)

    assert fold(gone, create(lamport=5), move(2.0, lamport=6)).to_ops() == [gone]


def test_a_repeated_delete_keeps_the_oldest_whichever_arrives_first():
    older, newer_one = delete(lamport=3), delete(lamport=8, origin=B)

    assert fold(create(), older, newer_one).to_ops() == [older]
    assert fold(create(), newer_one, older).to_ops() == [older]


def test_a_delete_leaves_other_objects_alone():
    keep = move(1.0, obj=Y, lamport=4)

    state = fold(create(), create(obj=Y), keep, delete())

    assert state.to_ops() == [create(obj=Y), keep, delete()]


# -- create -------------------------------------------------------------------------------


def test_the_first_create_wins_and_a_retry_changes_nothing():
    first = create(lamport=2, name="First")

    assert fold(first, create(lamport=9, name="Retry")).to_ops() == [first]


# -- to_ops and storage -------------------------------------------------------------------


def test_to_ops_lists_creates_then_sets_then_deletes_with_original_ids():
    ops = [
        move(1.0, obj=Y, lamport=6, origin=B),
        create(obj=X, lamport=2),
        delete(obj="33333333-3333-4333-8333-333333333333", lamport=4, origin=B),
        move(2.0, obj=X, lamport=7),
        create(obj=Y, lamport=5, origin=B),
    ]

    result = fold(*ops).to_ops()

    assert [op["kind"] for op in result] == ["create", "create", "set", "set", "delete"]
    assert [(op["lamport"], op["origin"]) for op in result] == [
        (2, A),
        (5, B),
        (6, B),
        (7, A),
        (4, B),
    ]


def test_an_empty_room_has_no_ops():
    assert RoomState().to_ops() == []
    assert RoomState.from_json(RoomState().to_json()) == RoomState()


def test_json_round_trip_keeps_the_state_and_its_order():
    state = fold(create(), create(obj=Y, origin=B), move(1.0), delete(obj=Y, lamport=9))

    restored = RoomState.from_json(state.to_json())

    assert restored.to_ops() == state.to_ops()
    assert json.loads(state.to_json()) == {"ops": state.to_ops()}


def test_folding_to_ops_again_changes_nothing():
    state = fold(create(), move(1.0, lamport=5), move(3.0, lamport=4, origin=B, prop="scale"))

    assert RoomState().apply_all(state.to_ops()) == state


# -- random sequences ---------------------------------------------------------------------

OBJECTS = [f"{n:08d}-0000-4000-8000-000000000000" for n in range(4)]
ORIGINS = [A, B, "cccccccc-cccc-4ccc-8ccc-cccccccccccc"]


def _random_ops(rng: random.Random, count: int) -> list[dict]:
    """Random ops over a few objects. Every op ID is unique, and a repeated create for an ID
    is an exact retry, as it is in practice (IDs are UUIDs)."""
    creates = {
        obj: create(obj=obj, lamport=rng.randint(1, 20), origin=rng.choice(ORIGINS))
        for obj in OBJECTS
    }
    ops, used = [], set()
    while len(ops) < count:
        obj, kind = rng.choice(OBJECTS), rng.choices(["set", "create", "delete"], [8, 2, 1])[0]
        if kind == "create":
            ops.append(creates[obj])
            continue
        op_id = (rng.randint(1, 40), rng.choice(ORIGINS))
        if op_id in used:
            continue
        used.add(op_id)
        if kind == "delete":
            ops.append(delete(obj=obj, lamport=op_id[0], origin=op_id[1]))
        else:
            prop = rng.choice(["location", "scale"])
            ops.append(move(rng.random(), obj=obj, lamport=op_id[0], origin=op_id[1], prop=prop))
    return ops


def _canonical(state: RoomState) -> list[str]:
    return sorted(json.dumps(op, sort_keys=True) for op in state.to_ops())


@pytest.mark.parametrize("seed", range(200))
def test_snapshot_plus_tail_equals_one_fold(seed):
    rng = random.Random(seed)
    ops = _random_ops(rng, 40)
    cut = rng.randint(0, len(ops))

    whole = RoomState().apply_all(ops)
    snapshot = RoomState.from_json(RoomState().apply_all(ops[:cut]).to_json())
    resumed = snapshot.apply_all(ops[cut:])

    assert resumed == whole


@pytest.mark.parametrize("seed", range(200))
def test_the_state_does_not_depend_on_arrival_order(seed):
    # Not required for catch-up (the log is folded in seq order), but it's what lets every
    # client converge however its ops arrived: #21 builds on this.
    rng = random.Random(seed)
    ops = _random_ops(rng, 40)
    shuffled = ops[:]
    rng.shuffle(shuffled)

    assert _canonical(RoomState().apply_all(shuffled)) == _canonical(RoomState().apply_all(ops))
