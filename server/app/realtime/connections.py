"""Tracks which sockets are in which room and broadcasts operations to them.

Knows nothing about operation contents; ordering and validation live in app.sync.
"""

# TODO: ConnectionManager with join(room_id, socket), leave(...), broadcast(room_id, message, exclude)
