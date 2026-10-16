"""WebSocket connection to the relay server.

Blender's UI must never block on the network, so the socket runs on a background
thread and hands messages to the main thread through a queue drained by bpy.app.timers.
(bpy may only be touched from the main thread.)
"""

# TODO: connect(url, room_id, token), send(operation), a thread-safe inbox queue, disconnect().
