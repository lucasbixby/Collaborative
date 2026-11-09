"""REST: create rooms, invite people, list a user's rooms, manage members (#18).

A room must be created before anyone can join it, and its creator is its owner. Room ids stay
human-readable ("demo"), since that's what people type into the Blender panel. Only owners
invite, change roles and remove people, and a room always keeps at least one owner. Anyone may
remove themselves (leave), except the last owner.

Invites: the owner gets a random code once; only its SHA-256 is stored. A code works for anyone
who has it, any number of times, until it expires or is revoked: a link to paste into a chat.
Joining with a code never lowers a role someone already has.

A role change or a removal also reaches the user's open sockets at once
(app.realtime.websocket.member_changed): a removed member is closed with 4403, and a new role
applies from their next message, so a downgraded editor stays connected as a viewer.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Body, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth.dependencies import CurrentUser, Session
from app.auth.membership import ROOM_ID_PATTERN, Member, Membership
from app.auth.permissions import Role, can_manage, higher
from app.db.models import Invite, Room, RoomMember, User
from app.realtime.websocket import member_changed

router = APIRouter()

MAX_INVITE_HOURS = 30 * 24


class CreateRoom(BaseModel):
    room_id: str = Field(pattern=ROOM_ID_PATTERN)


class RoomOut(BaseModel):
    room_id: str
    role: Role
    created_at: datetime


class MemberOut(BaseModel):
    username: str
    role: Role
    joined_at: datetime


class RoomDetail(RoomOut):
    members: list[MemberOut]


class CreateInvite(BaseModel):
    role: Literal[Role.EDITOR, Role.VIEWER]
    expires_in_hours: int = Field(24, ge=1, le=MAX_INVITE_HOURS)


class InviteOut(BaseModel):
    code: str
    room_id: str
    role: Role
    expires_at: datetime


class Joined(BaseModel):
    room_id: str
    role: Role


def _code_hash(code: str) -> str:
    # A code is 128 random bits, so a fast hash is enough: there's nothing to guess.
    return hashlib.sha256(code.encode()).hexdigest()


def _require_owner(member: Membership) -> None:
    if not can_manage(member.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only an owner can do that")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_room(body: CreateRoom, user: CurrentUser, session: Session) -> RoomOut:
    now = datetime.now(UTC)
    session.add(Room(id=body.room_id, created_by=user.id, created_at=now))
    session.add(RoomMember(room_id=body.room_id, user_id=user.id, role=Role.OWNER, joined_at=now))
    try:
        await session.commit()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, f"room {body.room_id!r} exists") from None
    return RoomOut(room_id=body.room_id, role=Role.OWNER, created_at=now)


@router.get("")
async def my_rooms(user: CurrentUser, session: Session) -> list[RoomOut]:
    rows = await session.execute(
        select(Room, RoomMember.role)
        .join(RoomMember, RoomMember.room_id == Room.id)
        .where(RoomMember.user_id == user.id)
        .order_by(Room.id)
    )
    return [RoomOut(room_id=room.id, role=role, created_at=room.created_at) for room, role in rows]


@router.get("/{room_id}")
async def get_room(member: Member, session: Session) -> RoomDetail:
    rows = await session.execute(
        select(User.username, RoomMember.role, RoomMember.joined_at)
        .join(User, User.id == RoomMember.user_id)
        .where(RoomMember.room_id == member.room.id)
        .order_by(User.username)
    )
    return RoomDetail(
        room_id=member.room.id,
        role=member.role,
        created_at=member.room.created_at,
        members=[MemberOut(username=u, role=r, joined_at=j) for u, r, j in rows],
    )


@router.post("/{room_id}/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(body: CreateInvite, member: Member, session: Session) -> InviteOut:
    _require_owner(member)
    code = secrets.token_urlsafe(16)
    now = datetime.now(UTC)
    invite = Invite(
        code_hash=_code_hash(code),
        room_id=member.room.id,
        role=body.role,
        created_by=member.user.id,
        created_at=now,
        expires_at=now + timedelta(hours=body.expires_in_hours),
        revoked=False,
    )
    session.add(invite)
    await session.commit()
    return InviteOut(code=code, room_id=invite.room_id, role=body.role, expires_at=invite.expires_at)


@router.delete("/{room_id}/invites/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(code: str, member: Member, session: Session) -> Response:
    _require_owner(member)
    invite = await session.scalar(
        select(Invite).where(Invite.code_hash == _code_hash(code), Invite.room_id == member.room.id)
    )
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such invite for this room")
    invite.revoked = True
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/join/{code}")
async def join_by_invite(code: str, user: CurrentUser, session: Session) -> Joined:
    invite = await session.scalar(select(Invite).where(Invite.code_hash == _code_hash(code)))
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such invite")
    if invite.revoked:
        raise HTTPException(status.HTTP_410_GONE, "this invite was revoked")
    if invite.expires_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_410_GONE, "this invite has expired")

    offered = Role(invite.role)
    membership = await session.get(RoomMember, (invite.room_id, user.id))
    if membership is None:
        membership = RoomMember(
            room_id=invite.room_id, user_id=user.id, role=offered, joined_at=datetime.now(UTC)
        )
        session.add(membership)
    else:
        membership.role = higher(Role(membership.role), offered)
    await session.commit()
    await member_changed(invite.room_id, user.id, Role(membership.role))
    return Joined(room_id=invite.room_id, role=membership.role)


async def _target(session, member: Membership, username: str) -> tuple[User, RoomMember]:
    user = await session.scalar(select(User).where(User.username == username.lower()))
    target = None if user is None else await session.get(RoomMember, (member.room.id, user.id))
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{username!r} isn't in this room")
    return user, target


async def _owner_count(session, room_id: str) -> int:
    return await session.scalar(
        select(func.count())
        .select_from(RoomMember)
        .where(RoomMember.room_id == room_id, RoomMember.role == Role.OWNER)
    )


async def _keep_an_owner(session, room_id: str, target: RoomMember) -> None:
    if target.role == Role.OWNER and await _owner_count(session, room_id) <= 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "a room needs an owner: make someone else owner first"
        )


@router.patch("/{room_id}/members/{username}")
async def change_role(
    username: str,
    role: Annotated[Role, Body(embed=True)],
    member: Member,
    session: Session,
) -> MemberOut:
    _require_owner(member)
    user, target = await _target(session, member, username)
    if role != Role.OWNER:
        await _keep_an_owner(session, member.room.id, target)
    target.role = role
    await session.commit()
    await member_changed(member.room.id, user.id, role)
    return MemberOut(username=user.username, role=role, joined_at=target.joined_at)


@router.delete("/{room_id}/members/{username}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(username: str, member: Member, session: Session) -> Response:
    if username.lower() != member.user.username:
        _require_owner(member)
    user, target = await _target(session, member, username)
    await _keep_an_owner(session, member.room.id, target)
    await session.delete(target)
    await session.commit()
    await member_changed(member.room.id, user.id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

