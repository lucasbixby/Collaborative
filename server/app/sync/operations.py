"""Operation format: the `ops` message from docs/protocol.md as Pydantic models.

`parse_message` turns raw JSON from a client into typed operations, rejecting anything the
spec doesn't allow; `serialize_message` turns them back into JSON for broadcasting.
Tests: server/tests/sync/test_operations.py.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import settings

# Every model uses this config:
#   extra="forbid"        unknown fields are errors (the schema's additionalProperties: false)
#   strict=True           no type coercion: "1.5" is not a number, true is not an integer
#   allow_inf_nan=False   NaN and Infinity are rejected
STRICT = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

# -- Building blocks ----------------------------------------------------------------------

# Lowercase, dashed UUIDs only. Pydantic's UUID type would also accept uppercase and
# dash-less forms, and IDs are compared as strings, so they must have exactly one spelling.
Uuid = Annotated[
    str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
]
Lamport = Annotated[int, Field(ge=1)]
Vec3 = tuple[float, float, float]
Vec4 = tuple[float, float, float, float]
Name = Annotated[str, Field(min_length=1, max_length=255)]

MAX_NAME_BYTES = 255  # Blender's own limit, in bytes of UTF-8


def _check_name_bytes(value: str) -> str:
    if len(value.encode("utf-8")) > MAX_NAME_BYTES:
        raise ValueError(f"name is longer than {MAX_NAME_BYTES} bytes of UTF-8")
    return value


# -- Rotation -----------------------------------------------------------------------------


class EulerRotation(BaseModel):
    """Euler angles in radians; `mode` is the axis order."""

    model_config = STRICT
    mode: Literal["XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"]
    values: Vec3


class FourValueRotation(BaseModel):
    """Quaternion `[w, x, y, z]` or axis-angle `[angle, x, y, z]`."""

    model_config = STRICT
    mode: Literal["QUATERNION", "AXIS_ANGLE"]
    values: Vec4


Rotation = Annotated[EulerRotation | FourValueRotation, Field(discriminator="mode")]

# -- Operations ---------------------------------------------------------------------------


class _OperationBase(BaseModel):
    """Fields every operation carries (D-025)."""

    model_config = STRICT
    object: Uuid
    lamport: Lamport
    origin: Uuid

    @property
    def op_id(self) -> tuple[int, str]:
        """(lamport, origin): unique per operation, and the order operations are applied in."""
        return (self.lamport, self.origin)


class SetVector(_OperationBase):
    kind: Literal["set"]
    property: Literal["location", "scale"]
    value: Vec3


class SetRotation(_OperationBase):
    kind: Literal["set"]
    property: Literal["rotation"]
    value: Rotation


class SetName(_OperationBase):
    kind: Literal["set"]
    property: Literal["name"]
    value: Name

    @field_validator("value")
    @classmethod
    def _name_fits_in_blender(cls, value: str) -> str:
        return _check_name_bytes(value)


SetOperation = Annotated[SetVector | SetRotation | SetName, Field(discriminator="property")]


class Transform(BaseModel):
    model_config = STRICT
    location: Vec3
    rotation: Rotation
    scale: Vec3


Face = Annotated[list[Annotated[int, Field(ge=0)]], Field(min_length=3)]


class Mesh(BaseModel):
    model_config = STRICT
    vertices: list[Vec3]
    faces: list[Face]


class CreateOperation(_OperationBase):
    kind: Literal["create"]
    name: Name
    object_type: Literal["MESH"]
    collection: Name
    transform: Transform
    mesh: Mesh

    @field_validator("name", "collection")
    @classmethod
    def _names_fit_in_blender(cls, value: str) -> str:
        return _check_name_bytes(value)

    @model_validator(mode="after")
    def _faces_point_at_existing_vertices(self) -> "CreateOperation":
        vertex_count = len(self.mesh.vertices)
        for face in self.mesh.faces:
            if max(face) >= vertex_count:
                raise ValueError(f"face {face} refers to a vertex that doesn't exist")
        return self


class DeleteOperation(_OperationBase):
    kind: Literal["delete"]


Operation = Annotated[SetOperation | CreateOperation | DeleteOperation, Field(discriminator="kind")]

# -- Message ------------------------------------------------------------------------------


class OpsMessage(BaseModel):
    """A batch of operations, applied in list order (D-024)."""

    model_config = STRICT
    v: Literal[1]
    type: Literal["ops"]
    ops: Annotated[list[Operation], Field(min_length=1)]


def parse_message(raw: str | bytes) -> OpsMessage:
    """Parse one `ops` message from a client.

    Raises ValueError (pydantic's ValidationError is a ValueError) for anything
    docs/protocol.md rejects, including messages larger than the configured limit.
    """
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    if len(data) > settings.max_operation_bytes:
        raise ValueError(
            f"message is {len(data)} bytes; the limit is {settings.max_operation_bytes}"
        )
    # Parsed by Pydantic directly, not json.loads first: Python's json module accepts NaN.
    return OpsMessage.model_validate_json(data)


def serialize_message(message: OpsMessage) -> str:
    """JSON text for a message, ready to send to clients."""
    return message.model_dump_json()
