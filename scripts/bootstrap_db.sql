-- Initial schemas + read-only role for the agent SQL tool.
create schema if not exists raw;
create schema if not exists analytics;

create table if not exists raw.contract_notices (
    ocid        text primary key,
    ingested_at timestamptz not null default now(),
    payload     jsonb not null
);

-- Least-privilege role used by the agent's SQL tool (marts read-only).
do $$
begin
    if not exists (select from pg_roles where rolname = 'agent_readonly') then
        create role agent_readonly login password 'change-me';
    end if;
end $$;
