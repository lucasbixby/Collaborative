"""Tests for serving the built web UI (#22): files, the SPA fallback, and what it never covers."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.accounts import ensure_room, sign_in
from tests.catchup import read_catch_up

INDEX = "<!doctype html><title>Collaborative</title><div id=root></div>"


@pytest.fixture
def web(database_url, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX)
    (dist / "assets" / "app-1a2b.js").write_text("console.log('app')")
    (tmp_path / "secret.txt").write_text("outside the build")
    with TestClient(create_app(database_url, web_dir=dist)) as test_client:
        yield test_client


def test_the_root_is_the_app(web):
    response = web.get("/")
    assert response.status_code == 200
    assert response.text == INDEX
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-cache"


def test_built_files_are_served(web):
    response = web.get("/assets/app-1a2b.js")
    assert response.status_code == 200
    assert response.text == "console.log('app')"


@pytest.mark.parametrize("path", ["/join/abc123", "/rooms/demo", "/signin", "/assets/missing.js"])
def test_client_routes_fall_back_to_the_app(web, path):
    response = web.get(path)
    assert response.status_code == 200
    assert response.text == INDEX


@pytest.mark.parametrize("path", ["/api/nope", "/api", "/api/rooms/demo/nothing-here", "/ws/rooms/demo"])
def test_api_and_socket_paths_never_fall_back(web, path):
    response = web.get(path)
    assert response.status_code in (401, 404, 405)
    assert response.headers["content-type"] == "application/json"


def test_the_api_and_health_still_answer(web):
    assert web.get("/health").json() == {"status": "ok"}
    assert web.get("/api/auth/me").status_code == 401
    assert web.get("/openapi.json").status_code == 200


def test_a_path_cant_escape_the_build_folder(web):
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/..%2f..%2fsecret.txt"):
        assert "outside the build" not in web.get(path).text


def test_without_a_build_the_server_is_api_only(database_url, tmp_path):
    with TestClient(create_app(database_url, web_dir=tmp_path / "missing")) as test_client:
        assert test_client.get("/").status_code == 404
        assert test_client.get("/health").status_code == 200


def test_the_socket_still_works_beside_the_catch_all(web):
    sign_in(web)
    ensure_room(web, "demo")
    with web.websocket_connect("/ws/rooms/demo") as ws:
        assert read_catch_up(ws) == ([], 0)
