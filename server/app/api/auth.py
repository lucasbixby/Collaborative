"""REST: account creation and sign-in. Issues the tokens the REST routes and the relay check.

Usernames are lowercased, so "Lucas" and "lucas" are one account. A wrong username and a wrong
password get the same error and take about as long, so neither says which accounts exist, and
repeated failures from one client are cut off.
"""

import asyncio
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, BeforeValidator, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import passwords
from app.auth.dependencies import CurrentUser, Session
from app.auth.tokens import create_token
from app.db.models import User

router = APIRouter()


def _lower(value):
    return value.strip().lower() if isinstance(value, str) else value


USERNAME_PATTERN = r"^[a-z0-9_.-]{3,32}$"
Username = Annotated[str, BeforeValidator(_lower), StringConstraints(pattern=USERNAME_PATTERN)]
Password = Annotated[
    str, Field(min_length=passwords.MIN_LENGTH, max_length=passwords.MAX_LENGTH)
]
LOGIN_FAILED = "wrong username or password"


class Credentials(BaseModel):
    username: Username
    password: Password


class LoginRequest(BaseModel):
    # Not the register rules: a password that would now be too short must still get the
    # generic error, not a 422 that says something about it.
    username: Annotated[str, BeforeValidator(_lower), Field(max_length=64)]
    password: Annotated[str, Field(max_length=passwords.MAX_LENGTH)]


class UserOut(BaseModel):
    id: int
    username: str
    created_at: datetime

    @classmethod
    def of(cls, user: User) -> "UserOut":
        return cls(id=user.id, username=user.username, created_at=user.created_at)


class LoginOut(BaseModel):
    token: str
    user: UserOut


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: Credentials, request: Request, session: Session) -> UserOut:
    # Every registration counts: each costs a scrypt hash, and accounts are free to make.
    limiter = request.app.state.register_limiter
    key = _client(request)
    limiter.check(key)
    limiter.fail(key)
    # scrypt takes ~50 ms of CPU: in a thread, so the relay isn't held up.
    password_hash = await asyncio.to_thread(passwords.hash_password, body.password)
    user = User(username=body.username, password_hash=password_hash, created_at=datetime.now(UTC))
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "that username is taken") from None
    return UserOut.of(user)


@router.post("/login")
async def login(body: LoginRequest, request: Request, session: Session) -> LoginOut:
    limiter = request.app.state.login_limiter
    key = f"{_client(request)}|{body.username}"
    limiter.check(key)
    user = await session.scalar(select(User).where(User.username == body.username))
    stored = user.password_hash if user is not None else passwords.DUMMY_HASH
    matches = await asyncio.to_thread(passwords.check_password, body.password, stored)
    if user is None or not matches:
        limiter.fail(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, LOGIN_FAILED)
    limiter.reset(key)
    return LoginOut(token=create_token(user.id), user=UserOut.of(user))


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.of(user)
