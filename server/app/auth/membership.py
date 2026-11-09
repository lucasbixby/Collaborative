"""Who is in which room, with which role (#17, #18): the lookups the REST routes and the relay
share, and the `member_of` dependency for routes under /api/rooms/{room_id}.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Room, RoomMember, User

from .dependencies import CurrentUser, Session
from .permissions import Role

ROOM_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"  # the socket URL's pattern too
RoomId = Annotated[str, Path(pattern=ROOM_ID_PATTERN)]


async def role_in(session: AsyncSession, room_id: str, user_id: int) -> Role | None:
    """The user's role in the room, or None if they aren't a member or there's no such room."""
    role = await session.scalar(
        select(RoomMember.role).where(RoomMember.room_id == room_id, RoomMember.user_id == user_id)
    )
    return Role(role) if role is not None else None


@dataclass
class Membership:
    room: Room
    user: User
    role: Role


async def member_of(room_id: RoomId, user: CurrentUser, session: Session) -> Membership:
    """The signed-in user's membership of the room in the path: 404 if there's no such room,
    403 if they aren't in it."""
    room = await session.get(Room, room_id)
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no room {room_id!r}")
    role = await role_in(session, room_id, user.id)
    if role is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"you aren't a member of {room_id!r}")
    return Membership(room, user, role)


Member = Annotated[Membership, Depends(member_of)]
