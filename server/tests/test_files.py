"""Tests for a room's project file: the host uploads the .blend, members download it."""

import pytest

from app.config import settings
from tests.accounts import bearer, ensure_room, join, token_for

ROOM = "studio"
BLEND = b"BLENDER-v405" + b"\x00" * 500
ZSTD_BLEND = b"\x28\xb5\x2f\xfd" + b"\x01" * 100


@pytest.fixture
def bob(client):
    """bob's headers: an editor in "studio", which tester (the client's own user) hosts."""
    ensure_room(client, ROOM)
    headers = bearer(token_for(client, "bob"))
    join(client, ROOM, headers)
    return headers


def _upload(client, content=BLEND, name="scene.blend", headers=None, room=ROOM):
    return client.put(f"/api/rooms/{room}/file", params={"name": name}, content=content, headers=headers)


def _stored_files():
    return [path for path in settings.asset_dir.rglob("*") if path.is_file()]


def test_a_room_starts_without_a_file(client, bob):
    assert client.get(f"/api/rooms/{ROOM}").json()["file"] is None
    assert client.get(f"/api/rooms/{ROOM}/file").status_code == 404


def test_the_host_uploads_and_every_member_downloads_the_same_bytes(client, bob):
    uploaded = _upload(client)

    assert uploaded.status_code == 200
    assert (uploaded.json()["name"], uploaded.json()["size"]) == ("scene.blend", len(BLEND))
    assert client.get("/api/rooms").json()[0]["file"] == uploaded.json()
    downloaded = client.get(f"/api/rooms/{ROOM}/file", headers=bob)
    assert downloaded.content == BLEND
    assert downloaded.headers["etag"] == f'"{uploaded.json()["hash"]}"'
    assert "scene.blend" in downloaded.headers["content-disposition"]


def test_only_the_host_uploads(client, bob):
    assert _upload(client, headers=bob).status_code == 403
    assert _stored_files() == []


def test_only_members_download(client, bob):
    _upload(client)
    outsider = bearer(token_for(client, "mallory"))
    assert client.get(f"/api/rooms/{ROOM}/file", headers=outsider).status_code == 403


@pytest.mark.parametrize("content", [b"", b"BLEN", b"PK\x03\x04 a zip file", b"<html>nope</html>"])
def test_something_that_isnt_a_blend_file_is_refused_and_not_kept(client, bob, content):
    assert _upload(client, content).status_code == 422
    assert _stored_files() == []


def test_a_compressed_blend_is_accepted(client, bob):
    assert _upload(client, ZSTD_BLEND).status_code == 200


def test_a_file_over_the_limit_is_refused_and_not_kept(client, bob, monkeypatch):
    monkeypatch.setattr(settings, "max_file_bytes", 100)
    assert _upload(client).status_code == 413
    assert _stored_files() == []


@pytest.mark.parametrize(
    ("given", "kept"),
    [
        ("../../etc/passwd", "passwd.blend"),
        ("C:\\Users\\lucas\\My Scene.blend", "My Scene.blend"),
        ("a<b>&c.blend", "a_b__c.blend"),
        ("", "project.blend"),
        ("...", "project.blend"),
    ],
)
def test_only_a_plain_file_name_is_kept(client, bob, given, kept):
    assert _upload(client, name=given).json()["name"] == kept


def test_a_new_upload_replaces_the_old_content(client, bob):
    first = _upload(client).json()
    second = _upload(client, BLEND + b"more").json()

    assert second["hash"] != first["hash"]
    assert client.get(f"/api/rooms/{ROOM}/file").content == BLEND + b"more"
    assert [path.name for path in _stored_files()] == [second["hash"]]


def test_two_rooms_can_share_content_and_deleting_one_keeps_it(client, bob):
    ensure_room(client, "other")
    _upload(client)
    _upload(client, room="other")
    assert len(_stored_files()) == 1

    assert client.delete("/api/rooms/other").status_code == 204
    assert client.get(f"/api/rooms/{ROOM}/file").content == BLEND

    assert client.delete(f"/api/rooms/{ROOM}").status_code == 204
    assert _stored_files() == []
