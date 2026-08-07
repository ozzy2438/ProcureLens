"""AusTender OCDS API client.

Fetches contract notices in OCDS schema and lands them as raw JSON rows in
Postgres (schema: raw.contract_notices). API docs:
https://github.com/austender/austender-ocds-api
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

import httpx
from sqlalchemy import JSON, Column, DateTime, MetaData, Table, Text, create_engine, func
from sqlalchemy.dialects.postgresql import insert

from procurelens.config import get_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.tenders.gov.au/ocds"
LANDING_BATCH_SIZE = 5_000


def _raw_table(metadata: MetaData) -> Table:
    return Table(
        "contract_notices",
        metadata,
        Column("release_id", Text, primary_key=True),
        Column("ocid", Text, nullable=False, index=True),
        Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("payload", JSON, nullable=False),
        schema="raw",
    )


def _ensure_release_grain(connection: object) -> None:
    """Create or migrate the raw table to one row per immutable OCDS release."""
    # `exec_driver_sql` is available on SQLAlchemy Connection. Keeping the migration here
    # makes an existing Week-1 database usable without dropping any landed payloads.
    connection.exec_driver_sql("create schema if not exists raw")  # type: ignore[attr-defined]
    connection.exec_driver_sql(  # type: ignore[attr-defined]
        """
        create table if not exists raw.contract_notices (
            release_id text primary key,
            ocid text not null,
            ingested_at timestamptz not null default now(),
            payload jsonb not null
        )
        """
    )
    connection.exec_driver_sql(  # type: ignore[attr-defined]
        """
        do $$
        begin
            if not exists (
                select 1
                from information_schema.columns
                where table_schema = 'raw'
                  and table_name = 'contract_notices'
                  and column_name = 'release_id'
            ) then
                alter table raw.contract_notices add column release_id text;
                update raw.contract_notices
                set release_id = payload ->> 'id'
                where release_id is null;

                if exists (
                    select 1 from raw.contract_notices where release_id is null
                ) then
                    raise exception 'Cannot migrate raw.contract_notices: payload.id is missing';
                end if;

                alter table raw.contract_notices alter column release_id set not null;
                alter table raw.contract_notices
                    drop constraint if exists contract_notices_pkey;
                alter table raw.contract_notices
                    add constraint contract_notices_pkey primary key (release_id);
            end if;
        end $$
        """
    )
    connection.exec_driver_sql(  # type: ignore[attr-defined]
        """
        do $$
        begin
            if not exists (
                select 1 from pg_indexes
                where schemaname = 'raw'
                  and tablename = 'contract_notices'
                  and indexname = 'ix_contract_notices_ocid'
            ) and exists (
                select 1
                from pg_class as relation
                inner join pg_namespace as namespace on namespace.oid = relation.relnamespace
                where namespace.nspname = 'raw'
                  and relation.relname = 'contract_notices'
                  and pg_get_userbyid(relation.relowner) = current_user
            ) then
                create index ix_contract_notices_ocid
                    on raw.contract_notices (ocid);
            end if;
        end $$
        """
    )


def fetch_contract_notices(start: date, end: date) -> list[dict]:
    """Fetch contract notices published between start and end (paginated)."""
    releases: list[dict] = []
    url: str | None = (
        f"{BASE_URL}/findByDates/contractPublished/"
        f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z"
    )
    transport = httpx.HTTPTransport(retries=3)
    with httpx.Client(
        timeout=httpx.Timeout(60, connect=10),
        transport=transport,
        headers={"User-Agent": "ProcureLens/0.1 (portfolio data engineering project)"},
    ) as client:
        while url:
            resp = client.get(url)
            resp.raise_for_status()
            payload = resp.json()
            releases.extend(payload.get("releases", []))
            next_url = payload.get("links", {}).get("next")
            url = urljoin(url, next_url) if next_url else None
            if len(releases) % 1_000 == 0 or url is None:
                logger.info("fetched %s releases so far", len(releases))
    return releases


def land_raw(releases: list[dict], database_url: str | None = None) -> int:
    """Insert OCDS releases idempotently; return the number of newly landed rows.

    OCDS permits many releases for one ``ocid``. The immutable release ``id`` is
    therefore the conflict key; using ``ocid`` would silently discard amendments.
    """
    if not releases:
        return 0

    rows: list[dict] = []
    for release in releases:
        release_id = release.get("id")
        ocid = release.get("ocid")
        if not release_id or not ocid:
            logger.warning("skipping OCDS release without id/ocid")
            continue
        rows.append({"release_id": str(release_id), "ocid": str(ocid), "payload": release})

    if not rows:
        return 0

    engine = create_engine(database_url or get_settings().database_url, pool_pre_ping=True)
    metadata = MetaData()
    contract_notices = _raw_table(metadata)
    inserted = 0

    with engine.begin() as connection:
        _ensure_release_grain(connection)
        for offset in range(0, len(rows), LANDING_BATCH_SIZE):
            batch = rows[offset : offset + LANDING_BATCH_SIZE]
            statement = insert(contract_notices).values(batch)
            statement = statement.on_conflict_do_nothing(index_elements=["release_id"])
            result = connection.execute(statement)
            inserted += max(result.rowcount or 0, 0)

    engine.dispose()
    logger.info("landed %s new releases (%s received)", inserted, len(rows))
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--last-days", type=int, default=None)
    parser.add_argument("--chunk-days", type=int, default=31)
    args = parser.parse_args()

    if args.last_days:
        end = datetime.utcnow().date()
        start = end - timedelta(days=args.last_days)
    else:
        if args.start is None or args.end is None:
            parser.error("provide both --start and --end, or use --last-days")
        start, end = args.start, args.end

    if start > end:
        parser.error("--start must be on or before --end")
    if args.chunk_days < 1:
        parser.error("--chunk-days must be positive")

    received_total = 0
    inserted_total = 0
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=args.chunk_days - 1), end)
        releases = fetch_contract_notices(chunk_start, chunk_end)
        received_total += len(releases)
        inserted_total += land_raw(releases)
        chunk_start = chunk_end + timedelta(days=1)

    logger.info(
        "ingestion complete: %s received, %s newly inserted",
        received_total,
        inserted_total,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    main()
