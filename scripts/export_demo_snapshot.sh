#!/usr/bin/env bash
set -euo pipefail

release_version="${RELEASE_VERSION:-1.0.0}"
expected_rows="${SNAPSHOT_EXPECTED_ROWS:-445029}"
source_database_url="${SOURCE_DATABASE_URL:-postgresql://procurelens:procurelens@localhost:5432/procurelens}"
output_path="${1:-data/snapshots/procurelens-marts-v${release_version}.dump}"
snapshot_schema="procurelens_release_snapshot"

command -v psql >/dev/null
command -v pg_dump >/dev/null
mkdir -p "$(dirname "${output_path}")"

cleanup() {
  psql --dbname="${source_database_url}" --set=ON_ERROR_STOP=1 \
    --command="drop schema if exists ${snapshot_schema} cascade" >/dev/null
}
trap cleanup EXIT

psql --dbname="${source_database_url}" --set=ON_ERROR_STOP=1 <<SQL
drop schema if exists ${snapshot_schema} cascade;
create schema ${snapshot_schema};

create table ${snapshot_schema}.fct_contracts as
select
    ocid,
    initial_release_id,
    agency,
    case
      when coalesce(supplier_id, supplier_name) is null then null
      else 'supplier-' || substr(md5('procurelens-v1|' || coalesce(supplier_id, supplier_name)), 1, 16)
    end as supplier_id,
    case
      when coalesce(supplier_id, supplier_name) is null then null
      else 'Supplier ' || upper(substr(md5('procurelens-v1|' || coalesce(supplier_id, supplier_name)), 1, 10))
    end as supplier_name,
    unspsc_code,
    procurement_method,
    case
      when unspsc_code is null then 'Australian Government procurement contract'
      else 'Australian Government procurement category ' || unspsc_code
    end as contract_description,
    award_date,
    contract_start_date,
    contract_end_date,
    award_value_aud,
    award_currency,
    value_confidentiality,
    description_confidentiality,
    amendment_count,
    first_upward_amendment_date,
    last_amendment_date,
    value_uplift_aud,
    was_amended_up
from analytics_marts.fct_contracts;

alter table ${snapshot_schema}.fct_contracts add primary key (ocid);
create index ix_release_snapshot_agency
    on ${snapshot_schema}.fct_contracts (agency);
create index ix_release_snapshot_supplier
    on ${snapshot_schema}.fct_contracts (supplier_name);

create table ${snapshot_schema}.dim_agencies as
select
    agency,
    count(*) as contracts_all_time,
    sum(award_value_aud) as total_spend_aud,
    avg(award_value_aud) as avg_contract_aud,
    max(award_date) as last_award_date
from ${snapshot_schema}.fct_contracts
where agency is not null
group by agency;

alter table ${snapshot_schema}.dim_agencies add primary key (agency);
analyze ${snapshot_schema}.fct_contracts;
analyze ${snapshot_schema}.dim_agencies;
SQL

actual_rows="$(psql --dbname="${source_database_url}" --tuples-only --no-align \
  --command="select count(*) from ${snapshot_schema}.fct_contracts")"
if [[ "${actual_rows}" != "${expected_rows}" ]]; then
  echo "Snapshot row check failed: expected ${expected_rows}, got ${actual_rows}" >&2
  exit 1
fi

pg_dump --dbname="${source_database_url}" \
  --format=custom --compress=9 --no-owner --no-privileges \
  --schema="${snapshot_schema}" --file="${output_path}"

if command -v sha256sum >/dev/null; then
  (cd "$(dirname "${output_path}")" && sha256sum "$(basename "${output_path}")") \
    > "${output_path}.sha256"
else
  checksum="$(shasum -a 256 "${output_path}" | awk '{print $1}')"
  printf '%s  %s\n' "${checksum}" "$(basename "${output_path}")" > "${output_path}.sha256"
fi

echo "Created ${output_path} (${actual_rows} pseudonymised contract rows)."
