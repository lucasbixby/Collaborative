"""Tests for login tokens and password hashing (#16)."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth import passwords
from app.auth.tokens import (
    ALGORITHM,
    InvalidToken,
    bearer_token,
    create_token,
    decode_token,
)
from app.config import settings


def test_a_token_round_trips_to_its_user_id():
    assert decode_token(create_token(42)) == 42


def test_a_tampered_token_is_refused():
    header, payload, signature = create_token(42).split(".")
    other_payload = create_token(7).split(".")[1]  # validly signed, but for a different body
    with pytest.raises(InvalidToken):
        decode_token(f"{header}.{other_payload}.{signature}")
    with pytest.raises(InvalidToken):
        decode_token(f"{header}.{payload}.{signature[:-2]}AA")


def test_an_expired_token_is_refused():
    long_ago = datetime.now(UTC) - timedelta(hours=settings.token_ttl_hours + 1)
    with pytest.raises(InvalidToken, match="expired"):
        decode_token(create_token(42, now=long_ago))


def test_a_token_signed_with_another_key_is_refused(monkeypatch):
    token = create_token(42)
    monkeypatch.setattr(settings, "secret_key", "a-different-key-entirely-0123456789")
    with pytest.raises(InvalidToken):
        decode_token(token)


def test_a_token_lasts_the_configured_time(monkeypatch):
    monkeypatch.setattr(settings, "token_ttl_hours", 2)
    claims = jwt.decode(create_token(1), settings.secret_key, algorithms=[ALGORITHM])
    assert claims["exp"] - claims["iat"] == 2 * 3600


def test_an_unsigned_token_is_refused():
    unsigned = jwt.encode({"sub": "1", "exp": datetime.now(UTC) + timedelta(hours=1)}, None, "none")
    with pytest.raises(InvalidToken):
        decode_token(unsigned)


@pytest.mark.parametrize("claims", [{"sub": "1"}, {"exp": 4102444800}, {"sub": "x", "exp": 4102444800}])
def test_a_token_without_a_usable_sub_or_exp_is_refused(claims):
    with pytest.raises(InvalidToken):
        decode_token(jwt.encode(claims, settings.secret_key, ALGORITHM))


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Bearer abc", "abc"),
        ("bearer abc ", "abc"),
        (None, None),
        ("", None),
        ("Basic abc", None),
        ("Bearer ", None),
        ("abc", None),
    ],
)
def test_bearer_token(header, expected):
    assert bearer_token(header) == expected


def test_a_password_verifies_against_its_hash():
    stored = passwords.hash_password("correct horse")
    assert passwords.check_password("correct horse", stored)
    assert not passwords.check_password("wrong horse", stored)


def test_the_stored_hash_is_not_the_password_and_is_salted():
    first = passwords.hash_password("correct horse")
    second = passwords.hash_password("correct horse")
    assert "correct horse" not in first
    assert first != second  # a fresh salt each time
    assert first.startswith(f"scrypt${passwords.N}${passwords.R}${passwords.P}$")


def test_a_hash_keeps_verifying_with_the_parameters_it_was_made_with(monkeypatch):
    monkeypatch.setattr(passwords, "N", 2**12)
    old = passwords.hash_password("correct horse")
    monkeypatch.undo()
    assert passwords.check_password("correct horse", old)


@pytest.mark.parametrize("stored", ["", "plain", "bcrypt$1$2$3$aa$bb", "scrypt$x$8$1$aa$bb"])
def test_a_malformed_hash_is_a_mismatch_not_an_error(stored):
    assert not passwords.check_password("anything", stored)
