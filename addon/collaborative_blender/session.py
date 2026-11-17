"""The session the Collaborative app launched this Blender into: which server, which room, and
who the user is there. The app passes it in environment variables; nothing is typed in Blender.

The token is taken out of the environment once read, so programs Blender starts don't inherit it.
"""

import os
from dataclasses import dataclass

DEFAULT_SERVER_URL = "ws://localhost:8000"


@dataclass
class Session:
    server_url: str = DEFAULT_SERVER_URL
    token: str = ""
    room: str = ""
    username: str = ""
    role: str = "editor"  # "owner" (the host), "editor" or "viewer"

    @property
    def is_host(self) -> bool:
        return self.role == "owner"

    @property
    def can_edit(self) -> bool:
        return self.role in ("owner", "editor")

    @property
    def http_url(self) -> str:
        """The REST side of the socket URL: ws:// -> http://, wss:// -> https://."""
        url = self.server_url.strip().rstrip("/")
        return "http" + url[2:] if url.startswith(("ws://", "wss://")) else url


def _from_environment() -> Session:
    env = os.environ
    return Session(
        server_url=env.get("COLLAB_SERVER_URL", DEFAULT_SERVER_URL),
        token=env.pop("COLLAB_TOKEN", ""),
        room=env.get("COLLAB_ROOM", ""),
        username=env.get("COLLAB_USERNAME", ""),
        role=env.get("COLLAB_ROLE", "editor"),
    )


current = _from_environment()


def configure(**values) -> Session:
    """Replace the session (tests and dev scripts; the app uses the environment)."""
    global current
    current = Session(**values)
    return current
