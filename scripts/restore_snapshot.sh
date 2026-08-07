#!/usr/bin/env bash
set -euo pipefail

snapshot_path="${SNAPSHOT_PATH:-/snapshot/procurelens-marts-v1.0.0.dump}"
checksum_path="${SNAPSHOT_CHECKSUM_PATH:-${snapshot_path}.sha256}"
expected_rows="${SNAPSHOT_EXPECTED_ROWS:-445029}"
snapshot_schema="procurelens_release_snapshot"
target_schema="analytics_marts"

: "${PGHOST:=db}"
: "${PGPORT:=5432}"
: "${PGUSER:=procurelens}"
: "${PGDATABASE:=procurelens}"
export PGHOST PGPORT PGUSER PGDATABASE

if [[ ! -f "${snapshot_path}" || ! -f "${checksum_path}" ]]; then
  echo "Snapshot or checksum is missing at ${snapshot_path}" >&2
  exit 2
fi

if command -v sha256sum >/dev/null; then
  (cd "$(dirname "${snapshot_path}")" && sha256sum --check "$(basename "${checksum_path}")")
else
  expected_hash="$(awk '{print $1}' "${checksum_path}")"
  actual_hash="$(shasum -a 256 "${snapshot_path}" | awk '{print $1}')"
  [[ "${actual_hash}" == "${expected_hash}" ]]
fi

until pg_isready --quiet; do
  sleep 1
done

psql --set=ON_ERROR_STOP=1 \
  --command="drop schema if exists ${snapshot_schema} cascade" >/dev/null
pg_restore --exit-on-error --no-owner --no-privileges \
  --dbname="${PGDATABASE}" "${snapshot_path}"

actual_rows="$(psql --tuples-only --no-align \
  --command="select count(*) from ${snapshot_schema}.fct_contracts")"
if [[ "${actual_rows}" != "${expected_rows}" ]]; then
  echo "Restored snapshot row check failed: expected ${expected_rows}, got ${actual_rows}" >&2
  exit 3
fi

psql --set=ON_ERROR_STOP=1 <<SQL
begin;
drop schema if exists ${target_schema} cascade;
alter schema ${snapshot_schema} rename to ${target_schema};
grant usage on schema ${target_schema} to agent_readonly;
grant select on all tables in schema ${target_schema} to agent_readonly;
alter default privileges for role procurelens in schema ${target_schema}
    grant select on tables to agent_readonly;
commit;
SQL

psql --set=ON_ERROR_STOP=1 --set=agent_password="${AGENT_DB_PASSWORD:-change-me}" <<'SQL'
alter role agent_readonly password :'agent_password';
SQL

agency_rows="$(psql --tuples-only --no-align \
  --command="select count(*) from ${target_schema}.dim_agencies")"
echo "Snapshot restore complete: ${actual_rows} contracts, ${agency_rows} agencies."
