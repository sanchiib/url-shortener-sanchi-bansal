"""
Configuration loaded from environment variables (see .env.example).
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file automatically so Config has access to variables regardless of entry point
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class Config:
    # Supabase project URL and service_role key (Project Settings > API).
    # The service_role key is secret — server-side only, never expose it
    # to a browser/frontend.
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY", "")
    )

    # Required to hit DELETE /<code> for links that have no owner, and
    # always works as an admin override for any link.
    MASTER_API_KEY = os.environ.get("MASTER_API_KEY", "dev-master-key-change-me")

    # Used to build the full short URL returned by POST /shorten.
    BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")

    # Length (in base62 characters) of generated short codes.
    CODE_LENGTH = _env_int("CODE_LENGTH", 7)

    # Manual rate limiting for POST /shorten: N requests per IP per window.
    RATE_LIMIT_MAX = _env_int("RATE_LIMIT_MAX", 10)
    RATE_LIMIT_WINDOW = _env_int("RATE_LIMIT_WINDOW", 60)  # seconds
