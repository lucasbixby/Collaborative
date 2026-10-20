"""Tests for the operation format (#7), written from docs/protocol.md.

These tests are the contract for `app/sync/operations.py`. It must provide:

    parse_message(raw: str | bytes) -> message
        Parse one `ops` message. Raise ValueError (pydantic's ValidationError is one) for
        anything protocol.md rejects, including messages over settings.max_operation_bytes.

    serialize_message(message) -> str
        Turn a parsed message back into JSON text that parse_message accepts.

The example messages are read straight from docs/protocol.md, so if the spec and the code
drift apart, these tests fail.
"""

import copy
import json
import re
from pathlib import Path

import pytest

from app.config import settings
from app.sync.operations import parse_message, serialize_message

PROTOCOL_MD = Path(__file__).resolve().parents[3] / "docs" / "protocol.md"


def _json_blocks():
    """Every ```json block in protocol.md, parsed (```jsonc blocks are skipped)."""
    text = PROTOCOL_MD.read_text(encoding="utf-8")
    return [json.loads(block) for block in re.findall(r"```json\n(.*?)```", text, re.DOTALL)]


def _example_messages():
    """The example `ops` messages, plus the lone `set` example wrapped in a batch."""
    blocks = _json_blocks()
    messages = [b for b in blocks if b.get("type") == "ops"]
    lone_ops = [b for b in blocks if "kind" in b]
    messages += [{"v": 1, "type": "ops", "ops": [op]} for op in lone_ops]
    return messages


EXAMPLES = _example_messages()
EXAMPLE_IDS = [
    "+".join(op["kind"] + (f":{op['property']}" if "property" in op else "") for op in m["ops"])
    for m in EXAMPLES
]


def _example(kind, prop=None):
    """A one-operation message built from the first matching example operation."""
    for message in EXAMPLES:
        for op in message["ops"]:
            if op["kind"] == kind and (prop is None or op.get("property") == prop):
                return {"v": 1, "type": "ops", "ops": [copy.deepcopy(op)]}
    raise LookupError(f"protocol.md has no example for {kind} {prop or ''}")


def _mutated(kind, change, prop=None):
    """JSON text of an example message after applying `change` to its first operation."""
    message = _example(kind, prop)
    change(message["ops"][0], message)
    # json.dumps writes NaN / Infinity for non-finite floats, which lets us test rejecting them.
    return json.dumps(message)


def test_the_spec_has_examples_to_test():
    kinds = {op["kind"] for m in EXAMPLES for op in m["ops"]}
    assert {"set", "create", "delete"} <= kinds


# 1. Every example in protocol.md parses -------------------------------------------------


@pytest.mark.parametrize("example", EXAMPLES, ids=EXAMPLE_IDS)
def test_protocol_examples_parse(example):
    message = parse_message(json.dumps(example))

    assert len(message.ops) == len(example["ops"])
    for parsed, original in zip(message.ops, example["ops"]):
        assert parsed.kind == original["kind"]
        assert parsed.object == original["object"]
        assert parsed.lamport == original["lamport"]
        assert parsed.origin == original["origin"]


def test_parse_accepts_bytes():
    raw = json.dumps(EXAMPLES[0]).encode("utf-8")
    assert len(parse_message(raw).ops) == len(EXAMPLES[0]["ops"])


# 2. Round trip ---------------------------------------------------------------------------


@pytest.mark.parametrize("example", EXAMPLES, ids=EXAMPLE_IDS)
def test_round_trip(example):
    first = parse_message(json.dumps(example))
    text = serialize_message(first)

    assert isinstance(text, str)
    assert parse_message(text) == first
    # Serializing must not add, drop or rename anything. (1 == 1.0 in Python, so integer
    # coordinates coming back as floats still compare equal.)
    assert json.loads(text) == example


# 3. Rejections from the spec -------------------------------------------------------------


UPPERCASE_UUID = "6C1F2A9E-3B4D-4E5F-8A7B-9C0D1E2F3A4B"


def _set_value(value):
    return lambda op, _: op.update(value=value)


def _set_field(**fields):
    return lambda op, _: op.update(**fields)


REJECTED = {
    # wrong shapes and sizes
    "location with 2 numbers": ("set", _set_value([1.0, 2.0]), "location"),
    "location with 4 numbers": ("set", _set_value([1.0, 2.0, 3.0, 4.0]), "location"),
    "number sent as a string": ("set", _set_value(["1.0", 2.0, 3.0]), "location"),
    "value is a string": ("set", _set_value("1,2,3"), "location"),
    "name given a vector": ("set", _set_field(property="name"), "location"),
    "quaternion with 3 values": (
        "set",
        lambda op, _: op["value"].update(mode="QUATERNION"),
        "rotation",
    ),
    "unknown rotation mode": ("set", lambda op, _: op["value"].update(mode="XYZW"), "rotation"),
    "rotation without mode": ("set", lambda op, _: op["value"].pop("mode"), "rotation"),
    # unknown or missing fields
    "unknown property": ("set", _set_field(property="hide_viewport"), "location"),
    "extra field on an operation": ("set", _set_field(extra=1), "location"),
    "missing origin": ("set", lambda op, _: op.pop("origin"), "location"),
    "unknown kind": ("set", _set_field(kind="move"), "location"),
    "delete with set fields": ("set", _set_field(kind="delete"), "location"),
    # Lamport timestamps
    "lamport 0": ("set", _set_field(lamport=0), "location"),
    "lamport negative": ("set", _set_field(lamport=-3), "location"),
    "lamport fractional": ("set", _set_field(lamport=1.5), "location"),
    "lamport true": ("set", _set_field(lamport=True), "location"),
    "lamport as a string": ("set", _set_field(lamport="42"), "location"),
    # IDs
    "object is a name, not a UUID": ("set", _set_field(object="Cube"), "location"),
    "object UUID in uppercase": ("set", _set_field(object=UPPERCASE_UUID), "location"),
    "origin UUID without dashes": (
        "set",
        _set_field(origin="0b7e5d218f3c4a6b9d2e1f4a5b6c7d8e"),
        "location",
    ),
    # numbers must be finite
    "NaN": ("set", _set_value([float("nan"), 0.0, 0.0]), "location"),
    "Infinity": ("set", _set_value([float("inf"), 0.0, 0.0]), "location"),
    # names
    "empty name": ("set", _set_field(property="name", value=""), "location"),
    "name over 255 characters": ("set", _set_field(property="name", value="a" * 256), "location"),
    "name over 255 bytes of UTF-8": (
        "set",
        _set_field(property="name", value="é" * 128),
        "location",
    ),
    # the envelope
    "protocol version 2": ("set", lambda _, m: m.update(v=2), "location"),
    "wrong message type": ("set", lambda _, m: m.update(type="join"), "location"),
    "empty batch": ("set", lambda _, m: m.update(ops=[]), "location"),
    "extra field on the message": ("set", lambda _, m: m.update(extra=True), "location"),
    # create
    "create without mesh": ("create", lambda op, _: op.pop("mesh"), None),
    "create of a non-mesh object": ("create", _set_field(object_type="CAMERA"), None),
    "face with 2 indices": ("create", lambda op, _: op["mesh"]["faces"].append([0, 1]), None),
    "face index out of range": (
        "create",
        lambda op, _: op["mesh"]["faces"].append([0, 1, 99]),
        None,
    ),
    "negative face index": ("create", lambda op, _: op["mesh"]["faces"].append([0, 1, -1]), None),
    "transform without scale": ("create", lambda op, _: op["transform"].pop("scale"), None),
    # delete
    "delete with a value": ("delete", _set_field(value=[0, 0, 0]), None),
}


@pytest.mark.parametrize(("kind", "change", "prop"), REJECTED.values(), ids=REJECTED.keys())
def test_rejects(kind, change, prop):
    raw = _mutated(kind, change, prop)
    with pytest.raises(ValueError):
        parse_message(raw)


@pytest.mark.parametrize(
    "raw",
    ["", "not json", "[]", "null", '{"v": 1}'],
    ids=["empty", "not JSON", "a list", "null", "no type or ops"],
)
def test_rejects_malformed_text(raw):
    with pytest.raises(ValueError):
        parse_message(raw)


def test_rejects_messages_over_the_size_limit():
    def add_many_vertices(op, _):
        op["mesh"]["vertices"] = [[0.123456789, 0.123456789, 0.123456789]] * 3000
        op["mesh"]["faces"] = [[0, 1, 2]]

    raw = _mutated("create", add_many_vertices)
    assert len(raw.encode("utf-8")) > settings.max_operation_bytes  # guard: really oversized

    with pytest.raises(ValueError):
        parse_message(raw)


# 4. What should pass ---------------------------------------------------------------------


ACCEPTED = {
    "quaternion rotation": (
        "set",
        _set_value({"mode": "QUATERNION", "values": [1.0, 0.0, 0.0, 0.0]}),
        "rotation",
    ),
    "axis-angle rotation": (
        "set",
        _set_value({"mode": "AXIS_ANGLE", "values": [0.5, 0.0, 0.0, 1.0]}),
        "rotation",
    ),
    "another Euler order (ZYX)": (
        "set",
        _set_value({"mode": "ZYX", "values": [0.1, 0.2, 0.3]}),
        "rotation",
    ),
    "rename": ("set", _set_field(property="name", value="Box"), "location"),
    "name of exactly 255 ASCII characters": (
        "set",
        _set_field(property="name", value="a" * 255),
        "location",
    ),
    "non-ASCII name within 255 bytes": (
        "set",
        _set_field(property="name", value="Würfel"),
        "location",
    ),
    "scale": ("set", _set_field(property="scale", value=[2.0, 2.0, 2.0]), "location"),
    "integer coordinates": ("set", _set_value([1, 2, 3]), "location"),
    "negative and tiny numbers": ("set", _set_value([-1e-9, -250.5, 0.0]), "location"),
    "large lamport": ("set", _set_field(lamport=2**53), "location"),
    "create with no faces (points only)": (
        "create",
        lambda op, _: op["mesh"].update(faces=[]),
        None,
    ),
    "create with an n-gon": (
        "create",
        lambda op, _: op["mesh"]["faces"].append([0, 1, 3, 2, 6]),
        None,
    ),
    "create in the top-level collection": (
        "create",
        _set_field(collection="Scene Collection"),
        None,
    ),
}


@pytest.mark.parametrize(("kind", "change", "prop"), ACCEPTED.values(), ids=ACCEPTED.keys())
def test_accepts(kind, change, prop):
    raw = _mutated(kind, change, prop)
    message = parse_message(raw)
    assert message.ops[0].kind == kind


def test_batch_with_several_kinds_keeps_order():
    batch = {
        "v": 1,
        "type": "ops",
        "ops": [
            _example("create")["ops"][0],
            _example("set", "location")["ops"][0],
            _example("delete")["ops"][0],
        ],
    }
    message = parse_message(json.dumps(batch))
    assert [op.kind for op in message.ops] == ["create", "set", "delete"]


def test_integer_coordinates_parse_as_numbers():
    message = parse_message(_mutated("set", _set_value([1, 2, 3]), "location"))
    assert [float(x) for x in message.ops[0].value] == [1.0, 2.0, 3.0]
