"""REST: host a room, join one by name and password, list my rooms, manage members.

A room is created by its host, who is its owner, with a password. Anyone signed in who knows
the name and password joins as an editor. Owners change roles, remove people and delete the
room; anyone but the last owner may leave. A role change or removal reaches the user's open
Blender connections at once (app.realtime.websocket.member_changed).

The room list is what the app's dashboard polls: each room carries who is connected from
Blender right now and, for its owners, the save requests waiting for an answer.
"""

import asyncio
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.auth import passwords
from app.auth.dependencies import CurrentUser, Session
from app.auth.membership import ROOM_ID_PATTERN, Member, Membership
from app.auth.permissions import Role, can_manage
from app.db.models import Operation, Room, RoomMember, Snapshot, User
from app.realtime.websocket import member_changed, presence, room_deleted, send_to_user

router = APIRouter()

RoomPassword = Annotated[str, Field(min_length=4, max_length=passwords.MAX_LENGTH)]
JOIN_FAILED = "wrong room name or password"


class CreateRoom(BaseModel):
    room_id: str = Field(pattern=ROOM_ID_PATTERN)
    password: RoomPassword


class JoinRoom(BaseModel):
    # Looser than CreateRoom: a bad name or password gets the one generic error, not a 422.
    room_id: str = Field(max_length=64)
    password: str = Field(max_length=passwords.MAX_LENGTH)


class FileOut(BaseModel):
    name: str
    size: int
    hash: str
    updated_at: datetime


class PresentUser(BaseModel):
    username: str
    role: Role
    connections: int


class SaveRequestOut(BaseModel):
    id: str
    username: str
    requested_at: datetime


class RoomOut(BaseModel):
    room_id: str
    role: Role
    host: str
    created_at: datetime
    file: FileOut | None
    online: list[PresentUser]
    save_requests: list[SaveRequestOut]


class MemberOut(BaseModel):
    username: str
    role: Role
    joined_at: datetime


class RoomDetail(RoomOut):
    members: list[MemberOut]


def file_of(room: Room) -> FileOut | None:
    if room.file_hash is None:
        return None
    return FileOut(
        name=room.file_name, size=room.file_size, hash=room.file_hash, updated_at=room.file_updated_at
    )


def _room_out(request: Request, room: Room, role: Role, host: str) -> RoomOut:
    saves = request.app.state.saves.pending(room.id) if can_manage(role) else []
    return RoomOut(
        room_id=room.id,
        role=role,
        host=host,
        created_at=room.created_at,
        file=file_of(room),
        online=presence(room.id),
        save_requests=[
            SaveRequestOut(id=save.id, username=save.username, requested_at=save.requested_at)
            for save in saves
        ],
    )


def _require_owner(member: Membership) -> None:
    if not can_manage(member.role):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the room's host can do that")


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_room(
    body: CreateRoom, request: Request, user: CurrentUser, session: Session
) -> RoomOut:
    now = datetime.now(UTC)
    password_hash = await asyncio.to_thread(passwords.hash_password, body.password)
    room = Room(id=body.room_id, created_by=user.id, created_at=now, password_hash=password_hash)
    session.add(room)
    session.add(RoomMember(room_id=body.room_id, user_id=user.id, role=Role.OWNER, joined_at=now))
    try:
        await session.commit()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, f"room {body.room_id!r} exists") from None
    return _room_out(request, room, Role.OWNER, user.username)


@router.get("")
async def my_rooms(request: Request, user: CurrentUser, session: Session) -> list[RoomOut]:
    rows = await session.execute(
        select(Room, RoomMember.role, User.username)
        .join(RoomMember, RoomMember.room_id == Room.id)
        .join(User, User.id == Room.created_by)
        .where(RoomMember.user_id == user.id)
        .order_by(Room.id)
    )
    return [_room_out(request, room, Role(role), host) for room, role, host in rows]


@router.post("/join")
async def join_room(body: JoinRoom, request: Request, user: CurrentUser, session: Session) -> RoomOut:
    """Join by name and password, as an editor. A wrong name and a wrong password get the same
    answer and take about as long, and repeated failures are cut off, per client and per user."""
    limiter = request.app.state.join_limiter
    keys = (f"ip:{_client(request)}", f"user:{user.id}")
    for key in keys:
        limiter.check(key)
    room = await session.get(Room, body.room_id)
    stored = room.password_hash if room is not None and room.password_hash else passwords.DUMMY_HASH
    matches = await asyncio.to_thread(passwords.check_password, body.password, stored)
    if room is None or room.password_hash is None or not matches:
        for key in keys:
            limiter.fail(key)
        raise HTTPException(status.HTTP_403_FORBIDDEN, JOIN_FAILED)

    membership = await session.get(RoomMember, (room.id, user.id))
    if membership is None:
        membership = RoomMember(
            room_id=room.id, user_id=user.id, role=Role.EDITOR, joined_at=datetime.now(UTC)
        )
        session.add(membership)
        await session.commit()
    host = await session.scalar(select(User.username).where(User.id == room.created_by))
    return _room_out(request, room, Role(membership.role), host)


@router.get("/{room_id}")
async def get_room(request: Request, member: Member, session: Session) -> RoomDetail:
    rows = await session.execute(
        select(User.username, RoomMember.role, RoomMember.joined_at)
        .join(User, User.id == RoomMember.user_id)
        .where(RoomMember.room_id == member.room.id)
        .order_by(RoomMember.joined_at, User.username)
    )
    host = await session.scalar(select(User.username).where(User.id == member.room.created_by))
    return RoomDetail(
        **_room_out(request, member.room, member.role, host).model_dump(),
        members=[MemberOut(username=u, role=r, joined_at=j) for u, r, j in rows],
    )


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(request: Request, member: Member, session: Session) -> Response:
    """Delete the room with its members, history and file, and disconnect everyone in it."""
    _require_owner(member)
    room = member.room
    file_hash = room.file_hash
    state = request.app.state
    # Under the room's lock, so no operation is appended while its history is being deleted;
    # one already waiting for the lock finds its connection closed and is dropped.
    async with state.room_locks[room.id]:
        for model in (Operation, Snapshot, RoomMember):
            await session.execute(delete(model).where(model.room_id == room.id))
        await session.delete(room)
        await session.commit()
        await room_deleted(room.id)
    state.room_locks.pop(room.id, None)
    state.saves.drop_room(room.id)
    state.snapshots.forget(room.id)
    if file_hash is not None:
        await _delete_file_if_unused(session, state.assets, file_hash)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _delete_file_if_unused(session, assets, file_hash: str) -> None:
    """Remove stored content no room points at any more (two rooms can share one file)."""
    still_used = await session.scalar(
        select(func.count()).select_from(Room).where(Room.file_hash == file_hash)
    )
    if not still_used:
        await assets.delete(file_hash)


async def _target(session, member: Membership, username: str) -> tuple[User, RoomMember]:
    user = await session.scalar(select(User).where(User.username == username.lower()))
    target = None if user is None else await session.get(RoomMember, (member.room.id, user.id))
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{username!r} isn't in this room")
    return user, target


async def _keep_an_owner(session, room_id: str, target: RoomMember) -> None:
    if target.role != Role.OWNER:
        return
    owners = await session.scalar(
        select(func.count())
        .select_from(RoomMember)
        .where(RoomMember.room_id == room_id, RoomMember.role == Role.OWNER)
    )
    if owners <= 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "a room needs a host: make someone else host first"
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
async def remove_member(
    username: str, request: Request, member: Member, session: Session
) -> Response:
    """An owner removes anyone; anyone removes themselves (leaves)."""
    if username.lower() != member.user.username:
        _require_owner(member)
    user, target = await _target(session, member, username)
    await _keep_an_owner(session, member.room.id, target)
    await session.delete(target)
    await session.commit()
    request.app.state.saves.drop_user(member.room.id, user.id)
    await member_changed(member.room.id, user.id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{room_id}/save-requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def answer_save_request(
    request_id: str,
    approve: Annotated[bool, Body(embed=True)],
    request: Request,
    member: Member,
) -> Response:
    """The host approves or denies a guest's save. Approving tells the host's own Blender to
    save the project file, so the host must have the room open there; if not, the request is
    kept and this is a 409."""
    _require_owner(member)
    room_id = member.room.id
    saves = request.app.state.saves
    pending = next((save for save in saves.pending(room_id) if save.id == request_id), None)
    if pending is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "that save request is gone")
    if approve:
        told = await send_to_user(
            room_id, member.user.id, {"v": 1, "type": "save", "requested_by": pending.username}
        )
        if not told:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "open this room in Blender first: the project is saved from your Blender",
            )
    saves.take(room_id, request_id)
    await send_to_user(
        room_id,
        pending.user_id,
        {"v": 1, "type": "save_result", "approved": approve, "by": member.user.username},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
