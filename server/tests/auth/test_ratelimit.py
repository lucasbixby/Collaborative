"""Tests for the attempt limiter and where sign-in and registration use it."""

import pytest
from fastapi import HTTPException

from app.auth.ratelimit import RateLimiter
from tests.accounts import PASSWORD, register


def test_the_limit_applies_per_key_and_slides_with_time():
    now = [0.0]
    limiter = RateLimiter(limit=2, window_seconds=60, clock=lambda: now[0])
    limiter.fail("a")
    now[0] = 30
    limiter.fail("a")

    with pytest.raises(HTTPException) as blocked:
        limiter.check("a")
    assert blocked.value.status_code == 429
    assert blocked.value.headers["Retry-After"] == "30"
    limiter.check("b")  # another key is unaffected

    now[0] = 61  # the first failure has aged out
    limiter.check("a")


def test_reset_clears_a_key():
    limiter = RateLimiter(limit=1, window_seconds=60)
    limiter.fail("a")
    limiter.reset("a")
    limiter.check("a")


def _login(anon, password, username="alice"):
    return anon.post("/api/auth/login", json={"username": username, "password": password})


def test_repeated_wrong_passwords_lock_that_name_for_that_client_only(anon):
    register(anon, "alice")
    register(anon, "bob")
    for _ in range(10):
        assert _login(anon, "wrong").status_code == 401

    assert _login(anon, PASSWORD).status_code == 429
    assert _login(anon, PASSWORD, "bob").status_code == 200


def test_a_successful_sign_in_clears_the_count(anon):
    register(anon, "alice")
    for _ in range(9):
        _login(anon, "wrong")
    assert _login(anon, PASSWORD).status_code == 200
    for _ in range(9):
        assert _login(anon, "wrong").status_code == 401


def test_registration_is_limited_per_client(anon):
    for number in range(30):
        register(anon, f"user{number}")
    response = anon.post("/api/auth/register", json={"username": "onemore", "password": PASSWORD})
    assert response.status_code == 429
