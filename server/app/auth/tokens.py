"""Login tokens: JWTs signed with HS256. A token carries the user's id and an expiry, and is
checked on every REST call and once per WebSocket connection. There is no revocation: signing
out only forgets the token on that machine."""

import os
import secrets
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import User

ALGORITHM = "HS256"
MIN_KEY_BYTES = 32  # RFC 7518 3.2, for HS256

# PyJWT repeats this on every call when the key is short; main.py says it once at startup.
warnings.filterwarnings("ignore", category=jwt.InsecureKeyLengthWarning)

_generated: dict[Path, str] = {}


class InvalidToken(Exception):
    """The token is malformed, wrongly signed, expired, or names no user."""


def signing_key() -> str:
    """COLLAB_SECRET_KEY if set, otherwise a random key created once and kept in
    `secret_key_file`, so a fresh install never signs tokens with a key anyone knows."""
    if settings.secret_key:
        return settings.secret_key
    path = settings.secret_key_file
    if path not in _generated:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # O_EXCL: if two processes start together, one creates the file and both read it.
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w") as file:
                file.write(secrets.token_urlsafe(48))
        _generated[path] = path.read_text().strip()
    return _generated[path]


def create_token(user_id: int, *, now: datetime | None = None) -> str:
    issued = now or datetime.now(UTC)
    expires = issued + timedelta(hours=settings.token_ttl_hours)
    claims = {"sub": str(user_id), "iat": issued, "exp": expires}
    return jwt.encode(claims, signing_key(), algorithm=ALGORITHM)


def decode_token(token: str) -> int:
    """The user id in a validly signed, unexpired token. Doesn't look the user up."""
    try:
        # `algorithms` is pinned, so a token can't choose its own (such as "none").
        claims = jwt.decode(
            token, signing_key(), algorithms=[ALGORITHM], options={"require": ["sub", "exp"]}
        )
        return int(claims["sub"])
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise InvalidToken(str(exc)) from exc


async def verify_token(session: AsyncSession, token: str) -> User:
    """The user a token belongs to. Raises InvalidToken if it's bad or the user is gone."""
    user = await session.get(User, decode_token(token))
    if user is None:
        raise InvalidToken("no such user")
    return user


def bearer_token(authorization: str | None) -> str | None:
    """The token in an `Authorization: Bearer <token>` header value, if there is one."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()
