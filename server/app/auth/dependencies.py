"""FastAPI dependencies shared by the REST routes: a database session and the signed-in user.

Every route except /health, register and login takes `CurrentUser`, so a missing, bad or expired
token is a 401 before the route runs.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User

from .tokens import InvalidToken, verify_token

# auto_error=False: FastAPI's own error here is a bare 403 in some versions; ours is a 401.
_bearer = HTTPBearer(auto_error=False, description="A token from POST /api/auth/login")


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session:
        yield session


Session = Annotated[AsyncSession, Depends(get_session)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"}
    )


async def current_user(
    session: Session,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise _unauthorized("sign in first: send Authorization: Bearer <token>")
    try:
        return await verify_token(session, credentials.credentials)
    except InvalidToken:
        raise _unauthorized("invalid or expired token; sign in again") from None


CurrentUser = Annotated[User, Depends(current_user)]
