"""
Input validation for URLs, custom aliases, and TTLs.
"""

import re
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}
ALIAS_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
MAX_URL_LENGTH = 2048

# Codes that would shadow a real route (GET /<code> is a catch-all single
# path segment, but we still reject these as *aliases* so nobody creates
# a link that's unreachable / confusing).
RESERVED_CODES = {
    "shorten",
    "stats",
    "analytics",
    "register",
    "my-links",
    "static",
    "health",
    "favicon.ico",
}


class ValidationError(Exception):
    """Raised for any user-facing input problem (400-level)."""


def validate_url(raw_url) -> str:
    if not isinstance(raw_url, str):
        raise ValidationError("`url` must be a string.")

    raw_url = raw_url.strip()
    if not raw_url:
        raise ValidationError("`url` cannot be empty.")
    if len(raw_url) > MAX_URL_LENGTH:
        raise ValidationError(f"`url` is too long (max {MAX_URL_LENGTH} characters).")
    if any(ord(ch) < 32 for ch in raw_url):
        raise ValidationError("`url` contains control characters.")

    parsed = urlparse(raw_url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ValidationError(
            f"Unsupported or missing scheme '{parsed.scheme or ''}'. "
            "Only http:// and https:// URLs are allowed."
        )
    if not parsed.netloc:
        raise ValidationError("URL is missing a valid host.")

    return raw_url


def validate_alias(alias) -> str:
    if not isinstance(alias, str):
        raise ValidationError("`alias` must be a string.")

    alias = alias.strip()
    if not ALIAS_RE.match(alias):
        raise ValidationError(
            "Alias must be 3-32 characters long and contain only letters, "
            "digits, hyphens, or underscores."
        )
    if alias.lower() in RESERVED_CODES:
        raise ValidationError(f"Alias '{alias}' is reserved and cannot be used.")

    return alias


def validate_ttl(ttl_seconds) -> "int | None":
    if ttl_seconds is None:
        return None
    try:
        ttl_seconds = int(ttl_seconds)
    except (TypeError, ValueError):
        raise ValidationError("`ttl_seconds` must be an integer.")
    if ttl_seconds <= 0:
        raise ValidationError("`ttl_seconds` must be a positive integer.")
    return ttl_seconds
