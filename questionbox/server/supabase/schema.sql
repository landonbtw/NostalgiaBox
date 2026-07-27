-- WonderBox database schema (run this in the Supabase SQL editor).
--
-- Two tables:
--   interactions  — the log of what was asked/answered (TEXT ONLY, never audio)
--   topic_rules   — the editable allow/deny/refuse safety rules
--
-- Row Level Security is ON for both, with NO permissive policies: only the
-- service role (used by the server) can read/write. The parent dashboard reads
-- via the server using the service role after authenticating the parent, so we
-- never expose this data to the anon/public key.

-- ---------------------------------------------------------------------------
-- interactions
-- ---------------------------------------------------------------------------
create table if not exists public.interactions (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  question    text,
  answer      text,
  mode        text not null check (mode in ('answered', 'deferred', 'refused')),
  category    text,
  reason      text,
  is_spelling boolean not null default false,
  spell_word  text,
  latency_ms  integer,
  device_id   text
);

create index if not exists interactions_created_at_idx
  on public.interactions (created_at desc);

alter table public.interactions enable row level security;
-- (no policies => only the service role can access)

-- ---------------------------------------------------------------------------
-- topic_rules (editable safety configuration)
-- ---------------------------------------------------------------------------
create table if not exists public.topic_rules (
  id         uuid primary key default gen_random_uuid(),
  kind       text not null check (kind in ('allow', 'deny', 'refuse')),
  rule_key   text not null,
  label      text not null,
  patterns   jsonb not null default '[]'::jsonb,  -- array of regex source strings
  enabled    boolean not null default true,
  sort       integer not null default 0,
  updated_at timestamptz not null default now(),
  unique (kind, rule_key)
);

alter table public.topic_rules enable row level security;
-- (no policies => only the service role can access)

-- Keep updated_at fresh on edits.
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists topic_rules_set_updated_at on public.topic_rules;
create trigger topic_rules_set_updated_at
  before update on public.topic_rules
  for each row execute function public.set_updated_at();
