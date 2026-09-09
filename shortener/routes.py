from flask import Blueprint, current_app, jsonify, redirect, render_template, request

from . import db as db_module
from . import repository as repo
from .codegen import generate_code
from .validation import ValidationError, validate_alias, validate_ttl, validate_url

bp = Blueprint("routes", __name__)


def build_short_url(code: str) -> str:
    base = current_app.config.get("BASE_URL") or "http://localhost:5000"
    try:
        if base in ("http://localhost:5000", "http://127.0.0.1:5000") and request:
            base = request.host_url.rstrip("/")
        else:
            base = base.rstrip("/")
    except Exception:
        base = base.rstrip("/")
    return f"{base}/{code}"


def get_requesting_user(db):
    """Resolve the caller's user row (or None) from the X-API-Key header."""
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return None
    return repo.find_user_by_api_key(db, api_key)


def row_to_dict(row, include_short_url=False):
    data = {
        "code": row["code"],
        "url": row["long_url"],
        "clicks": row["clicks"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "expired": repo.is_expired(row),
    }
    if include_short_url:
        data["short_url"] = build_short_url(row["code"])
    return data


# ---------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------

@bp.get("/")
def index():
    return render_template("index.html", base_url=current_app.config.get("BASE_URL", "http://localhost:5000"))


# ---------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------

@bp.post("/shorten")
def shorten():
    ip = request.remote_addr or "unknown"
    allowed, retry_after = current_app.rate_limiter.allow(ip)
    if not allowed:
        resp = jsonify(
            {"error": "Rate limit exceeded. Please slow down and try again shortly."}
        )
        resp.status_code = 429
        resp.headers["Retry-After"] = str(max(1, int(retry_after) + 1))
        return resp

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be JSON with a `url` field."}), 400

    db = db_module.get_db()

    try:
        long_url = validate_url(payload.get("url", ""))
        ttl_seconds = validate_ttl(payload.get("ttl_seconds"))

        alias = payload.get("alias")
        if alias:
            code = validate_alias(alias)
            if repo.code_exists(db, code):
                return jsonify({"error": f"Alias '{code}' is already taken."}), 409
        else:
            code = generate_code(
                lambda c: repo.code_exists(db, c),
                seed=long_url,
                length=current_app.config["CODE_LENGTH"],
            )
    except ValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500

    owner = get_requesting_user(db)
    try:
        row = repo.insert_url(
            db,
            code,
            long_url,
            ttl_seconds=ttl_seconds,
            owner_id=owner["id"] if owner else None,
        )
    except Exception as exc:
        return jsonify({"error": f"Failed to save URL: {str(exc)}"}), 500

    return (
        jsonify(
            {
                "code": row["code"],
                "short_url": build_short_url(row["code"]),
                "url": row["long_url"],
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
            }
        ),
        201,
    )


@bp.get("/stats/<code>")
def stats(code):
    db = db_module.get_db()
    row = repo.find_by_code(db, code)
    if row is None:
        return jsonify({"error": "Short code not found."}), 404
    return jsonify(row_to_dict(row))


@bp.delete("/<code>")
def delete(code):
    db = db_module.get_db()
    row = repo.find_by_code(db, code)
    if row is None:
        return jsonify({"error": "Short code not found."}), 404

    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return jsonify({"error": "Missing X-API-Key header."}), 401

    is_master = api_key == current_app.config["MASTER_API_KEY"]
    owner_ok = False
    if not is_master and row["owner_id"] is not None:
        user = repo.find_user_by_api_key(db, api_key)
        owner_ok = user is not None and user["id"] == row["owner_id"]

    if not (is_master or owner_ok):
        return jsonify({"error": "Invalid API key for this resource."}), 403

    repo.delete_url(db, code)
    return "", 204


# ---------------------------------------------------------------------
# Bonus: analytics dashboard
# ---------------------------------------------------------------------

@bp.get("/analytics")
def analytics():
    db = db_module.get_db()
    rows = repo.top_clicked(db, limit=5)
    data = [row_to_dict(r, include_short_url=True) for r in rows]

    wants_json = request.args.get("format") == "json" or request.accept_mimetypes.best == "application/json"
    if wants_json:
        return jsonify(data)
    return render_template("analytics.html", links=data, base_url=current_app.config["BASE_URL"])


# ---------------------------------------------------------------------
# Bonus: multi-user support
# ---------------------------------------------------------------------

@bp.post("/register")
def register():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    if not (3 <= len(username) <= 32):
        return jsonify({"error": "`username` must be 3-32 characters."}), 400

    db = db_module.get_db()
    if repo.find_user_by_username(db, username) is not None:
        return jsonify({"error": f"Username '{username}' is already taken."}), 409

    user = repo.create_user(db, username)
    return jsonify({"username": user["username"], "api_key": user["api_key"]}), 201


@bp.get("/my-links")
def my_links():
    db = db_module.get_db()
    user = get_requesting_user(db)
    if user is None:
        return jsonify({"error": "Missing or invalid X-API-Key header."}), 401

    rows = repo.urls_by_owner(db, user["id"])
    data = [row_to_dict(r, include_short_url=True) for r in rows]
    return jsonify({"username": user["username"], "links": data})


# ---------------------------------------------------------------------
# Redirect (kept last: it's a catch-all single path segment, but Flask
# always prefers a matching static rule like /analytics or /shorten
# over this dynamic one, regardless of registration order)
# ---------------------------------------------------------------------

@bp.get("/<code>")
def resolve(code):
    db = db_module.get_db()
    row = repo.find_by_code(db, code)
    if row is None:
        return jsonify({"error": "Short code not found."}), 404
    if repo.is_expired(row):
        return jsonify({"error": "This link has expired."}), 410

    repo.increment_clicks(db, code)
    return redirect(row["long_url"], code=302)
