"""
Query layer. Every function takes a Supabase client as its first
argument (mirrors the old sqlite3-connection-first signature), so
routes.py didn't need to change when the storage backend did.

Rows come back from Supabase as plain dicts, and dict["column"] works
the same way sqlite3.Row["column"] did, so callers are unaffected.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_ts(ts) -> datetime:
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    # Postgres/PostgREST can return a trailing "Z"; datetime.fromisoformat
    # only accepts that from Python 3.11+, so normalize it ourselves to
    # stay compatible with older Python versions too.
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))


def _first(res) -> Optional[dict]:
    return res.data[0] if res.data else None


# -- urls ----------------------------------------------------------------

def code_exists(db, code: str) -> bool:
    res = db.table("urls").select("id").eq("code", code).limit(1).execute()
    return bool(res.data)


def find_by_code(db, code: str) -> Optional[dict]:
    res = db.table("urls").select("*").eq("code", code).limit(1).execute()
    return _first(res)


def insert_url(
    db,
    code: str,
    long_url: str,
    ttl_seconds: Optional[int] = None,
    owner_id: Optional[int] = None,
) -> dict:
    created_at = now_iso()
    expires_at = None
    if ttl_seconds is not None:
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        ).isoformat(timespec="seconds")

    payload = {
        "code": code,
        "long_url": long_url,
        "created_at": created_at,
        "expires_at": expires_at,
        "clicks": 0,
        "owner_id": owner_id,
    }
    res = db.table("urls").insert(payload).execute()
    row = _first(res)
    if row is None:
        raise RuntimeError("Insert into `urls` did not return a row.")
    return row


def increment_clicks(db, code: str) -> None:
    # Calls the increment_clicks() SQL function (see schema.sql) so the
    # read-modify-write happens atomically on the database rather than
    # racing with other concurrent clicks in Python.
    try:
        db.rpc("increment_clicks", {"url_code": code}).execute()
    except Exception:
        # Fallback: direct update if RPC is unavailable or encounters an error
        try:
            row = find_by_code(db, code)
            if row:
                current_clicks = row.get("clicks") or 0
                db.table("urls").update({"clicks": current_clicks + 1}).eq("code", code).execute()
        except Exception:
            pass


def delete_url(db, code: str) -> bool:
    res = db.table("urls").delete().eq("code", code).execute()
    return bool(res.data)


def top_clicked(db, limit: int = 5):
    res = (
        db.table("urls")
        .select("*")
        .order("clicks", desc=True)
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    return res.data or []


def urls_by_owner(db, owner_id: int):
    res = (
        db.table("urls")
        .select("*")
        .eq("owner_id", owner_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def is_expired(row: dict) -> bool:
    expires_at = row.get("expires_at")
    if not expires_at:
        return False
    return datetime.now(timezone.utc) > _parse_ts(expires_at)


# -- users / api keys -----------------------------------------------------

def create_user(db, username: str) -> dict:
    api_key = secrets.token_urlsafe(24)
    created_at = now_iso()
    res = (
        db.table("users")
        .insert({"username": username, "api_key": api_key, "created_at": created_at})
        .execute()
    )
    row = _first(res)
    if row is None:
        raise RuntimeError("Insert into `users` did not return a row.")
    return row


def find_user_by_username(db, username: str) -> Optional[dict]:
    res = db.table("users").select("*").eq("username", username).limit(1).execute()
    return _first(res)


def find_user_by_api_key(db, api_key: str) -> Optional[dict]:
    res = db.table("users").select("*").eq("api_key", api_key).limit(1).execute()
    return _first(res)
