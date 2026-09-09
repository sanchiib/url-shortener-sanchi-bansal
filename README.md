# URL Shortener — Flask Web App

A Flask URL shortener with hash-based collision handling, custom aliases,
link expiry, **Supabase (Postgres) persistence**, API-key-protected
deletes, manual rate limiting, an analytics dashboard, and basic
multi-user support.

## Setup

### 1. Create the Supabase project & tables

1. Create a free project at [supabase.com](https://supabase.com).
2. Open **SQL Editor** in your project, paste the contents of
   [`schema.sql`](./schema.sql), and run it. This creates the `urls`
   and `users` tables, an index for the analytics query, and an
   `increment_clicks()` function used for atomic click counting.
3. Go to **Project Settings → API** and copy:
   - **Project URL** → `SUPABASE_URL`
   - **service_role key** (not the `anon` key) → `SUPABASE_SERVICE_ROLE_KEY`

   The service_role key is secret and bypasses Row Level Security — it's
   meant for trusted server-side code like this Flask app, and must
   never be sent to a browser or committed to git.

### 2. Run the app

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1

pip install -r requirements.txt

cp .env.example .env             # then fill in SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY
export $(grep -v '^#' .env | xargs)   # or just export the vars manually
                                       # (Windows: set them with $env:NAME="value")

python app.py                    # -> http://localhost:5000
```

Visit `http://localhost:5000` for the shorten form, or
`http://localhost:5000/analytics` for the top-5 dashboard.

Run the tests (these use an in-memory fake Supabase client, so they
never touch your real project):

```bash
pytest -v
```

## Configuration (environment variables)

| Variable                    | Default                     | Meaning                                            |
|-------------------------------|------------------------------|-----------------------------------------------------|
| `SUPABASE_URL`               | *(required)*                 | Your Supabase project URL.                          |
| `SUPABASE_SERVICE_ROLE_KEY`  | *(required)*                 | Service-role key — secret, server-side only.        |
| `MASTER_API_KEY`             | `dev-master-key-change-me`  | Admin key; can delete any link. **Change in prod.** |
| `BASE_URL`                   | `http://localhost:5000`     | Used to build the `short_url` returned by the API.  |
| `CODE_LENGTH`                | `7`                          | Length of generated (non-custom) short codes.       |
| `RATE_LIMIT_MAX`             | `10`                         | Max `POST /shorten` requests per IP per window.     |
| `RATE_LIMIT_WINDOW`          | `60`                         | Rate limit window, in seconds.                      |

## API documentation

All request/response bodies are JSON unless noted.

### `POST /shorten`

Create a short link.

**Request**
```json
{
  "url": "https://example.com/some/very/long/path",
  "alias": "my-link",       // optional, 3-32 chars, [A-Za-z0-9_-]
  "ttl_seconds": 3600        // optional, link expires after this many seconds
}
```

Optional header: `X-API-Key: <user's api key>` — if present and valid,
the created link is owned by that user (see [Multi-user](#multi-user-bonus)).

**Response — `201 Created`**
```json
{
  "code": "7KXdDod",
  "short_url": "http://localhost:5000/7KXdDod",
  "url": "https://example.com/some/very/long/path",
  "created_at": "2026-01-01T12:00:00+00:00",
  "expires_at": null
}
```

**Errors**
- `400` — missing/empty/malformed `url`, disallowed scheme (e.g. `javascript:`,
  `ftp:`), invalid `alias`, or invalid `ttl_seconds`.
- `409` — the requested `alias` is already taken.
- `429` — rate limit exceeded (see `Retry-After` header).

### `GET /<code>`

Redirects (`302`) to the original URL and increments its click counter
(via an atomic SQL function — see [Design decisions](#design-decisions)).

**Errors**
- `404` — unknown code.
- `410 Gone` — the link existed but its TTL has passed.

### `GET /stats/<code>`

**Response — `200 OK`**
```json
{
  "code": "7KXdDod",
  "url": "https://example.com/some/very/long/path",
  "clicks": 42,
  "created_at": "2026-01-01T12:00:00+00:00",
  "expires_at": null,
  "expired": false
}
```
`404` if the code doesn't exist. Note: stats remain viewable for expired
links (with `"expired": true`) — only the redirect itself returns `410`.

### `DELETE /<code>`

Requires header `X-API-Key: <key>`.

- If the link has no owner (created without a key), only the
  `MASTER_API_KEY` may delete it.
- If the link has an owner, either that user's own key **or** the
  `MASTER_API_KEY` may delete it.

**Responses**
- `204 No Content` — deleted.
- `401` — missing `X-API-Key` header.
- `403` — key provided but not authorized for this link.
- `404` — unknown code.

### `GET /analytics` (bonus)

Top 5 most-clicked links. Returns an HTML dashboard by default; add
`?format=json` (or `Accept: application/json`) for JSON:

```json
[
  {"code": "7KXdDod", "url": "https://example.com/...", "clicks": 42,
   "created_at": "...", "expires_at": null, "expired": false,
   "short_url": "http://localhost:5000/7KXdDod"}
]
```

### Multi-user (bonus)

- **`POST /register`** — `{"username": "alice"}` → `201`
  `{"username": "alice", "api_key": "..."}`. Usernames must be
  3-32 characters and unique (`409` on conflict).
- **`GET /my-links`** — header `X-API-Key: <key>` → `200`
  `{"username": "alice", "links": [...]}`, scoped to that user's own
  links only. `401` if the key is missing/invalid.
- Passing `X-API-Key` on `POST /shorten` attaches ownership to that link,
  enabling per-owner delete protection and `/my-links` filtering.
  Omitting it creates an anonymous link (deletable only with the
  master key).

## Design decisions

**Collision handling.** Codes are generated by hashing the long URL plus
an attempt counter and a few random bytes (SHA-256), base62-encoding
the digest, and taking the first `CODE_LENGTH` characters. Before
accepting a code we check Supabase for an existing row with that
code; on a collision we retry with a fresh salt (up to 8 attempts) so
retries explore a new part of the hash space rather than recomputing
the same collision. See `shortener/codegen.py`.

**Custom aliases.** Validated against `^[A-Za-z0-9_-]{3,32}$`, checked
for both uniqueness (`409` if taken) and a small reserved-word list
(`analytics`, `shorten`, `register`, etc.) so a custom alias can never
be confused with a real route.

**Expiry.** `ttl_seconds` is converted to an absolute `expires_at`
timestamp at creation time, so expiry checks are a simple timestamp
comparison. Only the redirect endpoint enforces `410`; `/stats/<code>`
still returns data (with an `expired` flag) since click history is
often still useful after a link has lapsed.

**Persistence — why Supabase, and how clicks stay accurate.** Supabase
gives us a real Postgres database behind a REST API, so the app has
no local file to manage or lose. The one thing that needs care moving
off a single-process sqlite file is the click counter: naively doing
"read clicks, add 1, write clicks" from Python races under concurrent
requests to the same link (two requests can both read `41` and both
write back `42`, losing a click). Instead, `GET /<code>` calls a
Postgres function, `increment_clicks(url_code)` (defined in
`schema.sql`), via `supabase.rpc(...)`, so the increment happens as a
single atomic `UPDATE ... SET clicks = clicks + 1` on the database
itself — no lost updates regardless of how many requests land at once.

**Auth.** A single `MASTER_API_KEY` (env var) acts as an admin
override for `DELETE`. Per-user API keys (`secrets.token_urlsafe(24)`)
are generated at `/register` and stored in the `users` table; they are
opaque bearer tokens, not JWTs, since the app has no session/login
flow to justify the extra complexity.

**Input validation.** URLs are parsed with `urllib.parse.urlparse` and
rejected unless the scheme is exactly `http` or `https` — this is what
blocks `javascript:`, `data:`, `file:`, etc. Control characters and
overlong URLs (>2048 chars) are also rejected.

**Rate limiting.** A small in-memory sliding-window limiter
(`shortener/ratelimiter.py`), keyed by remote IP, guards `POST
/shorten` only. It's intentionally dependency-free per the
constraints. It's process-local — fine for a single dev/demo process,
but wouldn't work for a rate limit shared across multiple workers/
processes without moving the counters to something shared (e.g. Redis,
or a Postgres table with the same atomic-RPC pattern used for clicks).

**Row Level Security.** The app talks to Supabase with the
`service_role` key, which bypasses RLS entirely — that's what lets a
single trusted backend manage every user's rows. `schema.sql` still
enables RLS on both tables with no policies defined, so if the
`anon`/public key were ever pointed at these tables from a browser, it
would see nothing by default.

## Project structure

```
url-shortener/
├── app.py                  # entry point
├── schema.sql               # run once in Supabase's SQL editor
├── shortener/
│   ├── __init__.py         # app factory
│   ├── config.py           # env-based config
│   ├── db.py                # Supabase client setup
│   ├── repository.py       # all Supabase queries
│   ├── codegen.py          # hash-based code generation
│   ├── validation.py       # URL/alias/TTL validation
│   ├── ratelimiter.py      # manual sliding-window limiter
│   └── routes.py           # all HTTP endpoints
├── templates/               # index + analytics dashboard
├── tests/
│   ├── fake_supabase.py    # in-memory Supabase stand-in for tests
│   ├── conftest.py
│   ├── test_units.py
│   └── test_app.py
├── requirements.txt
└── .env.example
```

## Known limitations

- Rate limiting is per-process; running multiple app workers would
  need a shared store (Redis, or a DB-backed counter like the click
  counter uses).
- No SSRF hardening (e.g. blocking `localhost`/private IP targets) —
  scheme validation only, per the stated requirement.
- API keys are stored in plaintext in the `users` table. Fine for a
  coursework/demo project; a production version should hash them at
  rest (e.g. store only a SHA-256 hash and compare hashes).
