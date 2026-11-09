"""Helpers for signing test clients in (#16) and making rooms (#18). The relay and catch-up tests
are about relaying, so their `client` is signed in as one user who owns every room it joins
(tests/catchup.py's `joined`); the access tests (tests/auth/) sign in several users and check
every refusal."""

PASSWORD = "correct horse battery"


def register(test_client, username: str, password: str = PASSWORD) -> None:
    """Create the account, or do nothing if it exists (a second app on the same database)."""
    response = test_client.post(
        "/api/auth/register", json={"username": username, "password": password}
    )
    assert response.status_code in (201, 409), response.text


def token_for(test_client, username: str, password: str = PASSWORD) -> str:
    """Register if needed, log in, and return the token."""
    register(test_client, username, password)
    response = test_client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def sign_in(test_client, username: str = "tester") -> str:
    """Make every later request and socket from `test_client` carry this user's token."""
    token = token_for(test_client, username)
    test_client.headers.update(bearer(token))
    return token


def ensure_room(test_client, room_id: str, headers: dict | None = None) -> None:
    """Create the room as the signed-in user, or do nothing if it exists already."""
    response = test_client.post("/api/rooms", json={"room_id": room_id}, headers=headers or {})
    assert response.status_code in (201, 409), response.text
