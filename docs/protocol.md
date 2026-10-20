# Wire protocol

The contract between the Blender add-on and the server. The add-on builds these messages as
plain dictionaries, and the server parses them with the models in
`server/app/sync/operations.py` (#7). Both sides follow this document; when they
disagree, this document is right and the code is fixed.

**Version 1** · status: operation messages specified; other message types are TODO.
Design decisions D-022 to D-026 in [devlog.md](devlog.md), based on the change-detection spike
([spike-notes.md](spike-notes.md)).

## Conventions

| Topic | Rule |
|---|---|
| Encoding | UTF-8 JSON text, one message per WebSocket frame |
| Units | Blender's internal units: metres for location, radians for Euler rotation, plain factors for scale |
| Object IDs | The object's `collab_id` (#4): a lowercase UUID string. Never the object's name, which can change |
| Client IDs (`origin`) | A UUID generated each time the add-on joins a room, so two Blenders on one computer have different IDs |
| Numbers | Finite only. `NaN` and `Infinity` are not valid JSON; senders serialize with `allow_nan=False`, receivers reject them |
| Size | A whole message is at most 64 KiB (`COLLAB_MAX_OPERATION_BYTES`) |

## Messages

Every message is an object with a protocol version `v` and a `type`.

| `type` | Direction | Purpose | Status |
|---|---|---|---|
| `ops` | add-on → server → other add-ons | A batch of operations | **Specified below** |
| `join` | add-on → server | Introduce the client (origin ID, last Lamport seen) | TODO with #11 |
| `catch_up` | add-on → server | Ask for operations missed while disconnected | TODO with #20 |
| `snapshot` | server → add-on | Full room state for a client that is too far behind | TODO with #20 |
| `error` | server → add-on | A message was rejected, and why | TODO with #10 |

### `ops`: a batch of operations

The add-on collects changes for about 50 ms and sends them together (D-019), so operations
always travel in a batch, applied in list order.

```jsonc
{
  "v": 1,
  "type": "ops",
  "ops": [ /* one or more operations */ ]
}
```

| Field | Type | Meaning |
|---|---|---|
| `v` | `1` | Protocol version |
| `type` | `"ops"` | Message type |
| `ops` | array of operations, at least one | The changes, oldest first |

The server forwards a batch to the other clients in the room unchanged.

## Operations

Every operation describes one change to one object, and carries everything needed to order it
on its own (D-025):

| Field | Type | Meaning |
|---|---|---|
| `kind` | `"set"`, `"create"` or `"delete"` | What happened |
| `object` | UUID string | The object's `collab_id` |
| `lamport` | integer ≥ 1 | The sender's Lamport timestamp for this change |
| `origin` | UUID string | The client that made the change |

The pair (`lamport`, `origin`) is unique per operation, so it doubles as the operation's ID.

### `set`: one property changed

One operation per property (D-022), so two people editing different properties of the same
object (one moves it, the other rotates it) both keep their change.

| `property` | `value` | Blender source |
|---|---|---|
| `location` | 3 numbers `[x, y, z]` | `obj.location` |
| `scale` | 3 numbers `[x, y, z]` | `obj.scale` |
| `rotation` | `{"mode": ..., "values": [...]}` (below) | `obj.rotation_mode` plus the matching rotation property |
| `name` | non-empty string, at most 255 characters (Blender's own limit is 255 bytes of UTF-8, so receivers also check the byte length) | `obj.name` |

**Rotation** sends the mode and the values together (D-023), so they can never disagree:

| `mode` | `values` | Blender property |
|---|---|---|
| `XYZ`, `XZY`, `YXZ`, `YZX`, `ZXY`, `ZYX` | 3 numbers, radians | `rotation_euler` |
| `QUATERNION` | 4 numbers `[w, x, y, z]` | `rotation_quaternion` |
| `AXIS_ANGLE` | 4 numbers `[angle, x, y, z]` | `rotation_axis_angle` |

Example:

```json
{
  "kind": "set",
  "object": "6c1f2a9e-3b4d-4e5f-8a7b-9c0d1e2f3a4b",
  "property": "location",
  "value": [1.0, 2.0, 0.5],
  "lamport": 42,
  "origin": "0b7e5d21-8f3c-4a6b-9d2e-1f4a5b6c7d8e"
}
```

### `create`: a new object

Carries everything another client needs to rebuild the object (D-021), because Blender's
updates don't say what kind of object was added.

| Field | Type | Meaning |
|---|---|---|
| `name` | string | The object's name when created |
| `object_type` | `"MESH"` | Only meshes for now; cameras, lights and empties come later |
| `collection` | string | Name of the collection it belongs to (`"Scene Collection"` is the scene's top level) |
| `transform` | `{"location": [3], "rotation": {...}, "scale": [3]}` | Same value shapes as `set` |
| `mesh.vertices` | array of `[x, y, z]` | Vertex positions in the object's local space |
| `mesh.faces` | array of arrays of vertex indices, at least 3 per face | Faces, as indices into `mesh.vertices` |

Plus the common fields. Duplicating an object (Shift+D) is sent as a `create` with a new
`collab_id`.

### `delete`: an object was removed

Only the common fields.

## Rules

1. **Ordering and conflicts.** Operations are ordered by (`lamport`, `origin`): higher Lamport
   wins, and on a tie the larger `origin` (string comparison) wins. For each (`object`,
   `property`), the last operation in that order is the value everyone ends up with
   (last-writer-wins, D-006). Implemented in #8 and #9.
2. **Deletes win (D-026).** Once an object is deleted, later `set` operations for it are
   ignored. Receivers remember deleted IDs (tombstones) so late-arriving operations stay ignored.
3. **Creates are idempotent.** A `create` for an ID that already exists is ignored.
4. **Strict validation (#10).** A message is rejected if it doesn't match the schema below,
   including any unknown field, property or rotation mode. Beyond the schema, receivers also
   check: face indices are less than the number of vertices; the whole message fits in 64 KiB;
   `origin` matches the client ID of the connection that sent it.
5. **Only allow-listed properties are ever applied.** Receivers map `property` to Blender
   attributes through a fixed table, never by passing the received name to `setattr`.
6. **Senders coalesce.** Within one batch there is at most one `set` per (`object`, `property`),
   carrying the latest value (D-019).
7. **Undo and redo are not special.** The add-on compares the scene with its cache after undo or
   redo (D-020) and sends whatever differs as ordinary operations.

## Not synced yet

- Moving an object to another collection after it's created
- Mesh edits after creation (stretch goal #26) and meshes over the size limit (#27)
- Cameras, lights, empties, materials, modifiers, parenting
- Selection, viewport and other per-user state (never synced)

## JSON Schema

The formal version of the `ops` message ([JSON Schema 2020-12](https://json-schema.org/)).
Tests on either side can validate example messages against it.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/lucasbixby/Collaborative/protocol/v1/ops",
  "title": "Collaborative ops message, protocol v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["v", "type", "ops"],
  "properties": {
    "v": { "const": 1 },
    "type": { "const": "ops" },
    "ops": { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/operation" } }
  },
  "$defs": {
    "uuid": {
      "type": "string",
      "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    },
    "lamport": { "type": "integer", "minimum": 1 },
    "vec3": {
      "type": "array", "items": { "type": "number" }, "minItems": 3, "maxItems": 3
    },
    "vec4": {
      "type": "array", "items": { "type": "number" }, "minItems": 4, "maxItems": 4
    },
    "name": { "type": "string", "minLength": 1, "maxLength": 255 },
    "rotation": {
      "oneOf": [
        {
          "type": "object", "additionalProperties": false, "required": ["mode", "values"],
          "properties": {
            "mode": { "enum": ["XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"] },
            "values": { "$ref": "#/$defs/vec3" }
          }
        },
        {
          "type": "object", "additionalProperties": false, "required": ["mode", "values"],
          "properties": {
            "mode": { "enum": ["QUATERNION", "AXIS_ANGLE"] },
            "values": { "$ref": "#/$defs/vec4" }
          }
        }
      ]
    },
    "operation": {
      "oneOf": [
        { "$ref": "#/$defs/set_vector" },
        { "$ref": "#/$defs/set_rotation" },
        { "$ref": "#/$defs/set_name" },
        { "$ref": "#/$defs/create" },
        { "$ref": "#/$defs/delete" }
      ]
    },
    "set_vector": {
      "type": "object", "additionalProperties": false,
      "required": ["kind", "object", "property", "value", "lamport", "origin"],
      "properties": {
        "kind": { "const": "set" },
        "object": { "$ref": "#/$defs/uuid" },
        "property": { "enum": ["location", "scale"] },
        "value": { "$ref": "#/$defs/vec3" },
        "lamport": { "$ref": "#/$defs/lamport" },
        "origin": { "$ref": "#/$defs/uuid" }
      }
    },
    "set_rotation": {
      "type": "object", "additionalProperties": false,
      "required": ["kind", "object", "property", "value", "lamport", "origin"],
      "properties": {
        "kind": { "const": "set" },
        "object": { "$ref": "#/$defs/uuid" },
        "property": { "const": "rotation" },
        "value": { "$ref": "#/$defs/rotation" },
        "lamport": { "$ref": "#/$defs/lamport" },
        "origin": { "$ref": "#/$defs/uuid" }
      }
    },
    "set_name": {
      "type": "object", "additionalProperties": false,
      "required": ["kind", "object", "property", "value", "lamport", "origin"],
      "properties": {
        "kind": { "const": "set" },
        "object": { "$ref": "#/$defs/uuid" },
        "property": { "const": "name" },
        "value": { "$ref": "#/$defs/name" },
        "lamport": { "$ref": "#/$defs/lamport" },
        "origin": { "$ref": "#/$defs/uuid" }
      }
    },
    "create": {
      "type": "object", "additionalProperties": false,
      "required": [
        "kind", "object", "lamport", "origin",
        "name", "object_type", "collection", "transform", "mesh"
      ],
      "properties": {
        "kind": { "const": "create" },
        "object": { "$ref": "#/$defs/uuid" },
        "lamport": { "$ref": "#/$defs/lamport" },
        "origin": { "$ref": "#/$defs/uuid" },
        "name": { "$ref": "#/$defs/name" },
        "object_type": { "const": "MESH" },
        "collection": { "$ref": "#/$defs/name" },
        "transform": {
          "type": "object", "additionalProperties": false,
          "required": ["location", "rotation", "scale"],
          "properties": {
            "location": { "$ref": "#/$defs/vec3" },
            "rotation": { "$ref": "#/$defs/rotation" },
            "scale": { "$ref": "#/$defs/vec3" }
          }
        },
        "mesh": {
          "type": "object", "additionalProperties": false,
          "required": ["vertices", "faces"],
          "properties": {
            "vertices": { "type": "array", "items": { "$ref": "#/$defs/vec3" } },
            "faces": {
              "type": "array",
              "items": {
                "type": "array", "minItems": 3,
                "items": { "type": "integer", "minimum": 0 }
              }
            }
          }
        }
      }
    },
    "delete": {
      "type": "object", "additionalProperties": false,
      "required": ["kind", "object", "lamport", "origin"],
      "properties": {
        "kind": { "const": "delete" },
        "object": { "$ref": "#/$defs/uuid" },
        "lamport": { "$ref": "#/$defs/lamport" },
        "origin": { "$ref": "#/$defs/uuid" }
      }
    }
  }
}
```

## Example messages

A drag and a rotation, coalesced into one batch:

```json
{
  "v": 1,
  "type": "ops",
  "ops": [
    {
      "kind": "set",
      "object": "6c1f2a9e-3b4d-4e5f-8a7b-9c0d1e2f3a4b",
      "property": "location",
      "value": [1.0, 2.0, 0.5],
      "lamport": 42,
      "origin": "0b7e5d21-8f3c-4a6b-9d2e-1f4a5b6c7d8e"
    },
    {
      "kind": "set",
      "object": "6c1f2a9e-3b4d-4e5f-8a7b-9c0d1e2f3a4b",
      "property": "rotation",
      "value": { "mode": "XYZ", "values": [0.0, 0.0, 1.5708] },
      "lamport": 43,
      "origin": "0b7e5d21-8f3c-4a6b-9d2e-1f4a5b6c7d8e"
    }
  ]
}
```

Adding a 2 m cube to the default collection:

```json
{
  "v": 1,
  "type": "ops",
  "ops": [
    {
      "kind": "create",
      "object": "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
      "lamport": 44,
      "origin": "0b7e5d21-8f3c-4a6b-9d2e-1f4a5b6c7d8e",
      "name": "Cube",
      "object_type": "MESH",
      "collection": "Collection",
      "transform": {
        "location": [0.0, 0.0, 0.0],
        "rotation": { "mode": "XYZ", "values": [0.0, 0.0, 0.0] },
        "scale": [1.0, 1.0, 1.0]
      },
      "mesh": {
        "vertices": [
          [1, 1, 1], [1, 1, -1], [1, -1, 1], [1, -1, -1],
          [-1, 1, 1], [-1, 1, -1], [-1, -1, 1], [-1, -1, -1]
        ],
        "faces": [
          [0, 4, 6, 2], [3, 2, 6, 7], [7, 6, 4, 5],
          [5, 1, 3, 7], [1, 0, 2, 3], [5, 4, 0, 1]
        ]
      }
    }
  ]
}
```

Deleting it:

```json
{
  "v": 1,
  "type": "ops",
  "ops": [
    {
      "kind": "delete",
      "object": "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
      "lamport": 45,
      "origin": "0b7e5d21-8f3c-4a6b-9d2e-1f4a5b6c7d8e"
    }
  ]
}
```

## Connection

`ws://<host>:8000/ws/rooms/{room_id}`, with the auth token sent on connect.

_TODO with #11 and #20: handshake (`join`), reconnect and catch-up sequence._
