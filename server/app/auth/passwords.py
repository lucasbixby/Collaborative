"""Password hashing with the standard library's scrypt (#16): no extra dependency.

A stored hash is `scrypt$<n>$<r>$<p>$<salt>$<key>` (salt and key in base64), so the parameters
travel with each hash: raising them later only affects new passwords, and old hashes still
verify. Each password gets its own random salt, so equal passwords don't give equal hashes.
"""

import base64
import hashlib
import hmac
import secrets

# n=2^14, r=8 needs 16 MiB and takes ~50 ms here: slow enough to make guessing expensive,
# fast enough for a sign-in. OpenSSL's default memory limit is 32 MiB, so this fits under it.
N, R, P = 2**14, 8, 1
SALT_BYTES = 16
KEY_BYTES = 32
MAXMEM = 64 * 1024 * 1024

MIN_LENGTH = 8
MAX_LENGTH = 256  # scrypt takes any length; this just stops someone posting megabytes


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=KEY_BYTES, maxmem=MAXMEM
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    key = _derive(password, salt, N, R, P)
    encode = base64.b64encode
    return f"scrypt${N}${R}${P}${encode(salt).decode()}${encode(key).decode()}"


def check_password(password: str, stored: str) -> bool:
    """Whether `password` matches `stored`, compared in constant time. A malformed hash is
    just a mismatch."""
    try:
        scheme, n, r, p, salt, key = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(key)
        actual = _derive(password, base64.b64decode(salt), int(n), int(r), int(p))
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


# Checked against when the username doesn't exist, so a wrong username takes as long as a wrong
# password and the response time doesn't reveal which accounts exist.
DUMMY_HASH = hash_password(secrets.token_hex(16))
