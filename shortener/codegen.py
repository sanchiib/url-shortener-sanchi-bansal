"""
Short-code generation.

Design: hash the long URL (plus an attempt counter and a few random
bytes) with SHA-256, base62-encode the first 8 bytes of the digest,
and take the first `length` characters as the code. We then check the
database for a collision; if the code is already taken we retry with a
fresh salt, up to `max_attempts` times. Because the salt changes every
attempt (and includes randomness), retries don't just recompute the
same collision - they explore a new part of the hash space each time.

This keeps code generation stateless (no counters/sequences to manage)
while still guaranteeing uniqueness is checked against real data,
rather than just assumed from a "good enough" hash.
"""

import hashlib
import os
import string

BASE62_ALPHABET = string.digits + string.ascii_lowercase + string.ascii_uppercase


def encode_base62(num: int) -> str:
    if num == 0:
        return BASE62_ALPHABET[0]
    digits = []
    base = len(BASE62_ALPHABET)
    while num:
        num, rem = divmod(num, base)
        digits.append(BASE62_ALPHABET[rem])
    return "".join(reversed(digits))


def generate_code(code_exists_fn, seed: str, length: int = 7, max_attempts: int = 8) -> str:
    """Return a short code not already reported taken by `code_exists_fn`.

    `code_exists_fn` is a callable(code) -> bool, so this function has no
    direct database dependency and is easy to unit test.
    """
    for attempt in range(max_attempts):
        salt = os.urandom(4)
        digest = hashlib.sha256(f"{seed}:{attempt}".encode("utf-8") + salt).digest()
        num = int.from_bytes(digest[:8], "big")
        code = encode_base62(num)[:length].zfill(length)
        if not code_exists_fn(code):
            return code
    raise RuntimeError("Could not generate a unique short code, please retry.")
