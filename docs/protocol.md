# Wire protocol

The contract between the Blender add-on and the server. Written by hand alongside
`server/app/sync/operations.py`; both sides must match this document.

## Operation

| Field | Meaning |
|---|---|
| `object` | Stable ID of the scene object |
| `property` | e.g. `location`, `rotation_euler`, `scale`, or `create` / `delete` |
| `value` | The new value |
| `lamport` | Lamport timestamp |
| `origin` | ID of the client that made the change (used to drop echoes) |

_TODO: exact JSON shape, object ID scheme, message types (op, ack, catch-up request, snapshot, error)._

## Connection

`ws://<host>:8000/ws/rooms/{room_id}` — auth token sent on connect.

_TODO: handshake, reconnect / catch-up sequence._
