"""Login tokens (#16): JWTs signed with HS256 and `settings.secret_key`. Passwords are in
passwords.py.

A token carries `sub` (the user's id, as a string, as the JWT spec wants) and `exp`. It's
checked on every REST call and once per WebSocket connection. There's no revocation list:
signing out only forgets the token on that machine, and it stays valid until `exp`.
"""

import warnings
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import User

ALGORITHM = "HS256"
MIN_KEY_BYTES = 32  # RFC 7518 3.2, for HS256

# PyJWT repeats this on every call when the key is short; main.py says it once at startup.
warnings.filterwarnings("ignore", category=jwt.InsecureKeyLengthWarning)


class InvalidToken(Exception):
    """The token is malformed, wrongly signed, expired, or names no user."""


def create_token(user_id: int, *, now: datetime | None = None) -> str:
    issued = now or datetime.now(UTC)
    expires = issued + timedelta(hours=settings.token_ttl_hours)
    claims = {"sub": str(user_id), "iat": issued, "exp": expires}
    return jwt.encode(claims, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> int:
    """The user id in a validly signed, unexpired token. Doesn't look the user up."""
    try:
        # `algorithms` is pinned, so a token can't choose its own (such as "none").
        claims = jwt.decode(
            token, settings.secret_key, algorithms=[ALGORITHM], options={"require": ["sub", "exp"]}
        )
        return int(claims["sub"])
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise InvalidToken(str(exc)) from exc


async def verify_token(session: AsyncSession, token: str) -> User:
    """The user a token belongs to. Raises InvalidToken for a bad signature, an expired token,
    or a user that doesn't exist (any more)."""
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
