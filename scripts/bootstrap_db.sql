-- Initial schemas + release-grain raw storage + read-only role for the agent SQL tool.
create schema if not exists raw;
create schema if not exists analytics;

create table if not exists raw.contract_notices (
    release_id  text primary key,
    ocid        text not null,
    ingested_at timestamptz not null default now(),
    payload     jsonb not null
);

create index if not exists ix_contract_notices_ocid
    on raw.contract_notices (ocid);

grant usage, create on schema raw, analytics to procurelens;
grant select, insert, update on all tables in schema raw to procurelens;
alter default privileges in schema raw
    grant select, insert, update on tables to procurelens;

-- Least-privilege role used by the agent's SQL tool (marts read-only).
do $$
begin
    if not exists (select from pg_roles where rolname = 'agent_readonly') then
        create role agent_readonly login password 'change-me';
    end if;
end $$;
