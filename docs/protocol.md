# Wire protocol

The contract between the Blender add-on and the server. The add-on builds these messages as
plain dictionaries, and the server parses them with the models in
`server/app/sync/operations.py` (#7). Both sides follow this document; when they
disagree, this document is right and the code is fixed.

**Version 1** · status: `ops`, `error` and `synced` specified, with catch-up on connect (#20)
and sign-in by header (#16, #17).
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
| `synced` | server → add-on | The room's catch-up is complete | **Specified below** (#20) |
| `error` | server → add-on | A message was rejected, and why | **Specified below** |

There's no `join` message: the token goes in the connection's `Authorization` header instead
(D-091; see [Access](#access)). There's no `catch_up` request and no `snapshot` message either:
the server sends every new connection the room's state as ordinary `ops` messages, then
`synced` (D-084; see [Connection](#connection)).

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

The server forwards a batch to every other client in the room, unchanged except for being
re-serialized from the parsed, validated message rather than the raw text (#11).

### `error`: a message was rejected

Sent to the sender only, in reply to one message that failed validation — bad schema,
unknown field, oversized, or any other rule under [Rules](#rules) below — that the server
couldn't save to its log, or that came from a viewer (`"viewers can't edit"`, [Access](#access)).
The connection stays open: one bad message doesn't disconnect a client.

```json
{
  "v": 1,
  "type": "error",
  "message": "ops.0.set.location.lamport: Input should be a valid integer"
}
```

| Field | Type | Meaning |
|---|---|---|
| `v` | `1` | Protocol version |
| `type` | `"error"` | Message type |
| `message` | string | Human-readable reason, for logs and debugging. Not meant to be parsed |

### `synced`: catch-up is complete

Sent once per connection, after the room's catch-up (see [Connection](#connection)). Everything
the client receives after it is live.

```json
{
  "v": 1,
  "type": "synced",
  "seq": 1234
}
```

| Field | Type | Meaning |
|---|---|---|
| `v` | `1` | Protocol version |
| `type` | `"synced"` | Message type |
| `seq` | integer, 0 or more | The last log `seq` the catch-up includes; 0 for a room with no operations |

## Operations

Every operation describes one change to one object, and carries everything needed to order it
on its own (D-025):

| Field | Type | Meaning |
|---|---|---|
| `kind` | `"set"`, `"create"` or `"delete"` | What happened |
| `object` | UUID string | The object's `collab_id` |
| `lamport` | integer from 1 to 2^63 − 1 | The sender's Lamport timestamp for this change |
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
| `mesh.vertices` | array of `[x, y, z]` | Vertex positions in the object's local space, rounded to 6 decimals |
| `mesh.faces` | array of arrays of vertex indices, at least 3 per face | Faces, as indices into `mesh.vertices` |

Plus the common fields. Duplicating an object (Shift+D, Alt+D) is sent as a `create` with a new
`collab_id`. The mesh is the base mesh, not the evaluated one: modifiers aren't synced.

**One `create` per message (#15).** Each `create` is sent as its own `ops` message, ahead of
the batch carrying that flush's `set`s and `delete`s. A big mesh then can't push the batch over
the size limit, and a receiver sees an object's `create` before any `set` for it. A `create`
whose message would exceed 64 KiB isn't sent at all (#27). The receiver links the object into
the named collection if this scene has one, otherwise the scene's top level, and Blender may
rename it (`Cube.001`) if the name is taken.

### `delete`: an object was removed

Only the common fields.

## Rules

1. **Ordering and conflicts.** Operations are ordered by (`lamport`, `origin`): higher Lamport
   wins, and on a tie the larger `origin` (string comparison) wins. For each (`object`,
   `property`), the last operation in that order is the value everyone ends up with
   (last-writer-wins, D-006). Client-side (#8 / #9): before applying an incoming `set`, a
   client checks it against the last value it sent or applied for that (`object`,
   `property`) — only a strictly newer one is applied; an older one, or a tie lost on
   `origin`, is skipped. Each client's own Lamport clock only ever moves forward: it ticks
   for its own edits and merges in (`max`) every timestamp it receives, and never resets,
   not even across rejoining. The server's log (#19) records arrival order as `seq`, which
   is the catch-up cursor, not a conflict rule. The server folds the log with these same rules
   to build a room's state for catch-up (#20); server ordering is #21.

   **A `create` counts as a write of what it carries (#20, D-081).** It sets `location`,
   `rotation`, `scale` and `name` at its own (`lamport`, `origin`), so a `set` older than the
   object's `create` loses. Live, every `set` from another client is newer anyway, because
   that client had to see the `create` first; the rule matters for a client that edits an
   object during catch-up and then offers it to the room (rule 10).
2. **Deletes win (D-026).** Once an object is deleted, later operations for it are ignored,
   whatever their timestamp. Clients remember deleted IDs (tombstones) so late-arriving
   operations stay ignored, including a `delete` for an ID they never had, whose `create` may
   still arrive. An ID is never reused: an object that comes back (Cmd+Z after a delete) gets
   a **new** `collab_id` and is sent as a new `create` (#15).
3. **Creates and deletes are idempotent.** A `create` for an ID that already exists or is
   tombstoned is ignored, and a repeated `delete` changes nothing.
4. **Strict validation (#10).** A message is rejected if it doesn't match the schema below,
   including any unknown field, property or rotation mode. Beyond the schema, receivers also
   check: face indices are less than the number of vertices; the whole message fits in 64 KiB;
   and every operation in a message has the same `origin`. The relay then checks that origin
   against the connection that sent it:
   - The first valid message pins the connection to its origin. A later message with a different
     origin gets an `error` and isn't relayed; the connection stays open.
   - An origin has one holder per room at a time, and the newest connection to claim it wins
     (D-062). A client reconnecting after a network drop reuses its origin, and the server may
     still think the old socket is alive. The older connection gets an `error` for anything it
     sends from then on. Closing a connection frees its origin, unless it has already moved on.
   - An origin belongs to the first user who sends as it, for good, across rooms and server
     restarts (#17, closing D-063). Every client in a room sees the others' origins, but another
     user claiming one gets `"origin … belongs to another user"`. The takeover above is only
     ever by the same user, which is what a reconnect is.
5. **Only allow-listed properties are ever applied.** Receivers map `property` to Blender
   attributes through a fixed table, never by passing the received name to `setattr`.
6. **Senders coalesce.** Within one batch there is at most one `set` per (`object`, `property`),
   carrying the latest value (D-019).
7. **Undo and redo are not special.** The add-on compares the scene with its cache after undo or
   redo (D-020) and sends whatever differs as ordinary operations.
8. **The relay saves, then forwards to everyone except the sender (#11, #19).** A valid `ops`
   message is appended to the room's operation log, one row per operation, and then goes to
   every other client currently in the room — never back to the sender, which has already
   applied its own change locally. An invalid message, or one the server couldn't save, gets an
   `error` reply instead, to the sender only: it isn't forwarded, and the connection stays open.

9. **A `set` for an unknown object is dropped, not buffered (D-057).** Each client's messages
   reach others in the order it sent them and its `create` goes first (see `create`), so this
   only happens to a client that missed the `create`. The object, if it arrives later, has the
   `create`'s values. A client that missed operations while disconnected gets them back from
   the catch-up on reconnect (#20).

10. **Merge on join (#20, D-085).** On the first `synced` after the user joins a room, the
    add-on sends a `create` for each local mesh object whose ID the catch-up didn't mention
    (in a `create`, `set` or `delete`), with the usual rules: one per message, size-checked,
    meshes only. A reconnect within the same Join sends nothing extra: edits made while
    disconnected are already queued. Edits made while not in a room at all are never sent,
    so an object the room already knows keeps the room's state on other clients.

## Not synced yet

- Moving an object to another collection after it's created
- Mesh edits after creation (stretch goal #26) and meshes over the size limit (#27)
- Cameras, lights, empties, materials, modifiers, parenting. A new non-mesh object is logged as
  `not synced yet` and sends no `create`
- Loose edges: `create` carries only vertices and faces, so a Circle arrives as bare vertices
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
    "lamport": { "type": "integer", "minimum": 1, "maximum": 9223372036854775807 },
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

`ws://<host>:8000/ws/rooms/{room_id}`, with the header `Authorization: Bearer <token>`.

`room_id` must match `^[A-Za-z0-9_-]{1,64}$`; the server closes the connection with code
`1008` otherwise. A room's connections exist only while at least one client is in it, but its
operations and snapshots are kept (#19, #20).

### Access (#16, #17)

The token comes from `POST /api/auth/login` (below) and goes in the `Authorization` header,
**never the URL**: URLs end up in access logs, and a token in a query string is ignored. The
server accepts the socket, checks the token and the user's role in the room, and if either
fails closes it **before any catch-up**:

| Close code | Reason text (for people) | Meaning | Client should |
|---|---|---|---|
| `4401` | `sign in first`, or `invalid or expired token; sign in again` | No token, a bad one, or an expired one | Stop reconnecting; ask the user to sign in |
| `4403` | `no access to room <id>` | The room doesn't exist, or the user isn't a member: the same reason for both, so it doesn't tell anyone which rooms exist | Stop reconnecting; the user needs an invite (or to create the room) |
| `4403` | `removed from room <id>` | An owner removed this user while connected | Same |

Retrying with the same token can only fail the same way, so the add-on stops instead of backing
off and retrying.

Roles, per room: **owner** > **editor** > **viewer**.

- Everyone in the room gets the catch-up and every live `ops`.
- An owner or editor may send `ops`.
- A viewer's `ops` get `{"type": "error", "message": "viewers can't edit"}`. They aren't
  parsed, logged or forwarded, and the connection stays open.
- A role change made over REST applies to open connections from their next message: a
  downgraded editor stays connected, as a viewer. A removed member's sockets are closed with
  `4403` (D-095).

### Catch-up on connect (#20)

Every new connection, whether it's a first join, a late join or a reconnect after a drop, gets
the same sequence, so a client never has to ask for what it missed (D-084):

1. The server adds the connection to the room.
2. It computes the room's current state: the latest snapshot, plus the log after it, folded with
   rules 1–3.
3. It sends that state as ordinary `ops` messages, with each operation's original `lamport` and
   `origin`: every `create` in a message of its own, then the winning `set`s, then one `delete`
   per deleted ID, so a client still holding a deleted object removes it and remembers the
   tombstone. `set`s and `delete`s are batched one origin per message (rule 4), and every
   message is at most 64 KiB.
4. It sends `synced`.

Then the connection is live. The server holds the room's lock (D-083) through steps 1–4 and
around "save → forward" (rule 8), so no live operation reaches a client before its catch-up,
and none falls between reading the state and joining. Duplicates are harmless, since operations
are idempotent under last-writer-wins and tombstones, but nothing is lost.

The client applies catch-up `ops` like any other (rules 1–3), and skips any of its own.

**Snapshots** are a cache over the log, which is never trimmed: one is written whenever a
room's log has grown `COLLAB_SNAPSHOT_EVERY` operations (default 500) past the last (D-082).

### REST

Every route except `/health`, register and login needs `Authorization: Bearer <token>`, or the
reply is `401`. `room_id` follows the same pattern as the socket, or the reply is `422`. Routes
under a room are for its members (`403`), and an unknown room is `404`.

**Accounts (#16).** Usernames are 3–32 of `a-z 0-9 . _ -`, lowercased (`Lucas` is `lucas`);
passwords are at least 8 characters.

| Request | Response |
|---|---|
| `POST /api/auth/register` `{"username", "password"}` | `201` `{"id", "username", "created_at"}`, or `409` if the name is taken |
| `POST /api/auth/login` `{"username", "password"}` | `{"token", "user": {...}}`, or `401` `wrong username or password`, the same for both |
| `GET /api/auth/me` | the signed-in user |

A token is valid for `COLLAB_TOKEN_TTL_HOURS` (default 168, one week). There's no revocation:
signing out forgets the token on that machine.

**Rooms (#18).** A room must be created before anyone can join it.

| Request | Who | Response |
|---|---|---|
| `POST /api/rooms` `{"room_id"}` | anyone signed in | `201`, the creator is owner; `409` if the id is taken |
| `GET /api/rooms` | anyone signed in | `[{"room_id", "role", "created_at"}]`: my rooms |
| `GET /api/rooms/{id}` | members | the room, my role, and `members: [{"username", "role", "joined_at"}]` |
| `POST /api/rooms/{id}/invites` `{"role": "editor" \| "viewer", "expires_in_hours": 24}` | owners | `201` `{"code", "room_id", "role", "expires_at"}`. 1–720 hours |
| `DELETE /api/rooms/{id}/invites/{code}` | owners | `204`; the code stops working |
| `POST /api/rooms/join/{code}` | anyone signed in | `{"room_id", "role"}`. `404` unknown code, `410` expired or revoked. A member keeps the higher of their role and the invite's |
| `PATCH /api/rooms/{id}/members/{username}` `{"role"}` | owners | the member's new role |
| `DELETE /api/rooms/{id}/members/{username}` | owners, or the member themselves | `204` |

An invite code works for anyone who has it, any number of times, until it expires or is
revoked. A room always keeps an owner: demoting or removing the last one is `409`.

**State (#20).** For members, viewers included.

| Request | Response |
|---|---|
| `GET /api/rooms/{room_id}/snapshot` | `{"room_id", "seq", "ops": [...]}`: the room's current state, the same operations catch-up sends, and the last `seq` included |
| `GET /api/rooms/{room_id}/operations?since=<seq>&limit=<n>` | `{"room_id", "operations": [{"seq", "received_at", "op"}]}`: log rows with `seq` above `since` (default 0), oldest first, at most `limit` (1–1000, default 1000). For the next page, pass the last row's `seq` |

The cursor is `seq`, the server's arrival order, never a Lamport time.
