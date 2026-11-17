"""Tests for the session the app hands Blender through the environment."""

import importlib
import os

import pytest


@pytest.fixture
def session(addon):
    return addon.session


def test_the_session_comes_from_the_environment_and_the_token_leaves_it(session, monkeypatch):
    monkeypatch.setenv("COLLAB_SERVER_URL", "wss://collab.example")
    monkeypatch.setenv("COLLAB_TOKEN", "t0k")
    monkeypatch.setenv("COLLAB_ROOM", "studio")
    monkeypatch.setenv("COLLAB_USERNAME", "lucas")
    monkeypatch.setenv("COLLAB_ROLE", "owner")

    current = importlib.reload(session).current

    assert (current.server_url, current.token, current.room) == ("wss://collab.example", "t0k", "studio")
    assert (current.username, current.is_host, current.can_edit) == ("lucas", True, True)
    assert "COLLAB_TOKEN" not in os.environ  # programs Blender starts don't inherit it


def test_without_the_app_there_is_no_room(session, monkeypatch):
    for name in ("COLLAB_SERVER_URL", "COLLAB_TOKEN", "COLLAB_ROOM", "COLLAB_ROLE"):
        monkeypatch.delenv(name, raising=False)

    current = importlib.reload(session).current

    assert (current.server_url, current.room, current.token) == ("ws://localhost:8000", "", "")


@pytest.mark.parametrize(
    ("role", "is_host", "can_edit"),
    [("owner", True, True), ("editor", False, True), ("viewer", False, False)],
)
def test_roles(session, role, is_host, can_edit):
    current = session.configure(role=role)
    assert (current.is_host, current.can_edit) == (is_host, can_edit)


@pytest.mark.parametrize(
    ("socket_url", "rest_url"),
    [
        ("ws://localhost:8000", "http://localhost:8000"),
        ("wss://collab.example/", "https://collab.example"),
        ("http://10.0.0.5:8000", "http://10.0.0.5:8000"),
    ],
)
def test_the_rest_address_follows_the_socket_address(session, socket_url, rest_url):
    assert session.configure(server_url=socket_url).http_url == rest_url
