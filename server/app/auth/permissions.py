"""Per-room permissions, enforced server-side (#17): owner > editor > viewer.

The checks take a role, or None for someone who isn't a member (or a room that doesn't exist),
so every caller asks the same question the same way. The relay asks once per connection and
keeps the role on the connection; a role change reaches open connections through
app.realtime.access.
"""

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"

    @property
    def rank(self) -> int:
        return _RANK[self]


_RANK = {Role.VIEWER: 0, Role.EDITOR: 1, Role.OWNER: 2}


def higher(first: Role, second: Role) -> Role:
    return first if first.rank >= second.rank else second


def can_join(role: Role | None) -> bool:
    """Connect to the room, get its catch-up and its live ops, and read it over REST."""
    return role is not None


def can_send_operations(role: Role | None) -> bool:
    return role in (Role.OWNER, Role.EDITOR)


def can_manage(role: Role | None) -> bool:
    """Invite people, change roles, and remove members."""
    return role == Role.OWNER
