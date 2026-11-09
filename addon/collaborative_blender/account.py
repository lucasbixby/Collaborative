"""Signing in to the server (#16): `POST /api/auth/login` with the standard library's urllib.

Blocking, but only for one short request from a button in Preferences, so it's called on the
main thread rather than through client.py's threads. The password is only passed through;
the token that comes back is what Preferences keeps.
"""

import json
import urllib.error
import urllib.request

LOGIN_TIMEOUT = 10  # seconds


class SignInError(Exception):
    """Sign-in failed, with a message to show the user."""


def http_url(server_url: str) -> str:
    """The REST side of the socket URL in Preferences: ws:// -> http://, wss:// -> https://."""
    url = server_url.strip().rstrip("/")
    if url.startswith(("ws://", "wss://")):
        return "http" + url[2:]
    return url


def login(server_url: str, username: str, password: str) -> tuple[str, str]:
    """Sign in and return (token, username as the server spells it)."""
    request = urllib.request.Request(
        f"{http_url(server_url)}/api/auth/login",
        data=json.dumps({"username": username, "password": password}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=LOGIN_TIMEOUT) as response:
            body = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise SignInError("Wrong username or password") from None
        raise SignInError(f"The server refused the sign-in (HTTP {exc.code})") from None
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise SignInError(f"Couldn't reach {http_url(server_url)}: {reason}") from None
    except ValueError:
        raise SignInError("The server's reply wasn't JSON; is the URL right?") from None
    try:
        return body["token"], body["user"]["username"]
    except (KeyError, TypeError):
        raise SignInError("The server's reply had no token; is the URL right?") from None
