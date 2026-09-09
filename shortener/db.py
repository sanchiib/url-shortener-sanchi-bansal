"""
Supabase client management.

Supabase's Python client talks to PostgREST over HTTPS — it's a
lightweight REST client, not a persistent database connection. Unlike
the old sqlite3 setup there's no per-request connection to open and
close; we create one client when the app starts and reuse it for
every request.
"""

from flask import Flask, current_app, g


def get_db():
    """Return the app's Supabase client (a supabase.Client)."""
    if "db" not in g:
        g.db = current_app.supabase
    return g.db


def init_app(app: Flask) -> None:
    # Imported here (not at module load time) so that importing this
    # module - and anything that imports it - doesn't require the
    # `supabase` package to be installed unless the app is actually
    # initialized. Keeps unit tests for unrelated modules lightweight.
    from supabase import create_client

    url = app.config["SUPABASE_URL"]
    key = app.config["SUPABASE_KEY"]
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set. "
            "Copy .env.example to .env, fill them in from your Supabase "
            "project's Settings > API page, and export them before "
            "running the app."
        )
    app.supabase = create_client(url, key)
