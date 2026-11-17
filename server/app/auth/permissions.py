"""Per-room permissions, enforced server-side: owner (the host) > editor > viewer.

The checks take a role, or None for someone who isn't a member, so every caller asks the same
question the same way.
"""

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"



def can_join(role: Role | None) -> bool:
    """Connect to the room, get its catch-up and its live ops, and read it over REST."""
    return role is not None


def can_send_operations(role: Role | None) -> bool:
    return role in (Role.OWNER, Role.EDITOR)


def can_manage(role: Role | None) -> bool:
    """Change roles, remove members, replace the project file, answer save requests, delete."""
    return role == Role.OWNER
