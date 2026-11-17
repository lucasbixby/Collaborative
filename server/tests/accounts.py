"""Helpers for signing test clients in and making rooms. The relay and catch-up tests are
about relaying, so their `client` is signed in as one user who owns every room it joins
(tests/catchup.py's `joined`); the access tests sign in several users and check every refusal."""

PASSWORD = "correct horse battery"
ROOM_PASSWORD = "open sesame"


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
    response = test_client.post(
        "/api/rooms", json={"room_id": room_id, "password": ROOM_PASSWORD}, headers=headers or {}
    )
    assert response.status_code in (201, 409), response.text


def join(test_client, room_id: str, headers: dict, role: str = "editor", owner: dict | None = None):
    """Join `room_id` as the user in `headers`. Joining makes an editor; any other role is then
    set by the room's owner (`owner` headers, or the client's own user)."""
    response = test_client.post(
        "/api/rooms/join", json={"room_id": room_id, "password": ROOM_PASSWORD}, headers=headers
    )
    assert response.status_code == 200, response.text
    if role != "editor":
        username = test_client.get("/api/auth/me", headers=headers).json()["username"]
        changed = test_client.patch(
            f"/api/rooms/{room_id}/members/{username}", json={"role": role}, headers=owner or {}
        )
        assert changed.status_code == 200, changed.text
    return response
