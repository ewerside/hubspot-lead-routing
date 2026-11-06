-- Unqualified names on purpose: the lead_routing role's search_path points to its own schema.

create table if not exists lead_log (
    submission_id text primary key,
    received_at timestamptz,
    email text,
    company text,
    score int check (score between 0 and 100),
    tier text check (tier in ('hot', 'warm', 'cold')),
    intent text,
    reason text,
    score_source text check (score_source in ('llm', 'rule')),
    path text not null check (path in ('new', 'duplicate', 'rejected')),
    hubspot_contact_id text,
    hubspot_deal_id text,
    alerted_at timestamptz
);

create table if not exists failed_leads (
    id serial primary key,
    submission_id text,
    failed_at timestamptz default now(),
    node text,
    error text,
    payload jsonb,
    replayed_at timestamptz
);
