-- Run this once in your Supabase project's SQL Editor
-- (Project → SQL Editor → New query → paste → Run).

create table if not exists users (
    id         bigint generated always as identity primary key,
    username   text not null unique,
    api_key    text not null unique,
    created_at timestamptz not null default now()
);

create table if not exists urls (
    id         bigint generated always as identity primary key,
    code       text not null unique,
    long_url   text not null,
    created_at timestamptz not null default now(),
    expires_at timestamptz,
    clicks     integer not null default 0,
    owner_id   bigint references users(id) on delete set null
);

create index if not exists idx_urls_owner  on urls (owner_id);
create index if not exists idx_urls_clicks on urls (clicks desc);

-- Atomic click counter. Doing "read clicks, add 1, write clicks" from
-- Python would race under concurrent clicks; this function increments
-- inside a single statement on the database instead. Called via
-- supabase.rpc("increment_clicks", {"url_code": code}).
create or replace function increment_clicks(url_code text)
returns void
language sql
as $$
  update urls set clicks = clicks + 1 where code = url_code;
$$;

-- The Flask app authenticates with the service_role key (server-side
-- only — never ship it to a browser), which bypasses Row Level
-- Security entirely. Enabling RLS here is still good practice in case
-- the anon/public key is ever pointed at these tables from elsewhere,
-- since with RLS on and no policies defined, the anon key sees nothing.
alter table users enable row level security;
alter table urls  enable row level security;
