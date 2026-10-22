"""Convergence test (#8 / #9): replicas that apply the same operations in different
orders must end up identical. Plain Python — simulates replicas as a values dict plus
their own `ordering.Versions`, with no Blender involved at all.
"""

import random

import pytest

from collaborative_blender import ordering

REPLICAS = ("A", "B", "C")
OBJECTS = ("obj-1", "obj-2")
PROPERTIES = ("x", "y")


def _generate_operations(rng: random.Random, count: int) -> list[dict]:
    """`count` operations, each "sent" by a random replica with that replica's own
    ever-increasing Lamport timestamp, so concurrent edits really do interleave."""
    clocks = {replica: ordering.LamportClock() for replica in REPLICAS}
    ops = []
    for _ in range(count):
        origin = rng.choice(REPLICAS)
        ops.append(
            {
                "object": rng.choice(OBJECTS),
                "property": rng.choice(PROPERTIES),
                "value": rng.randint(0, 1000),
                "lamport": clocks[origin].tick(),
                "origin": origin,
            }
        )
    return ops


def _apply_in_order(ops: list[dict]) -> dict[tuple[str, str], int]:
    """One replica applying `ops` in exactly the order given."""
    values: dict[tuple[str, str], int] = {}
    versions = ordering.Versions()
    for op in ops:
        key = (op["object"], op["property"])
        op_id = (op["lamport"], op["origin"])
        if versions.should_apply(key, op_id):
            values[key] = op["value"]
            versions.record(key, op_id)
    return values


@pytest.mark.parametrize("seed", range(10))
def test_replicas_converge_regardless_of_delivery_order(seed):
    rng = random.Random(seed)
    ops = _generate_operations(rng, count=50)

    results = []
    for _ in REPLICAS:
        shuffled = ops[:]
        rng.shuffle(shuffled)
        results.append(_apply_in_order(shuffled))

    assert all(result == results[0] for result in results[1:])
    assert results[0]  # sanity: the run actually produced some values
