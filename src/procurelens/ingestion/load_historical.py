"""Bulk-load historical AusTender contract data (1999+) from data.gov.au CSVs.

Dataset: https://data.gov.au/data/dataset/historical-australian-government-contract-data
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from pathlib import Path

import pandas as pd
from sqlalchemy import JSON, Column, MetaData, Table, Text, create_engine
from sqlalchemy.dialects.postgresql import insert

from procurelens.config import get_settings

logger = logging.getLogger(__name__)
CSV_CHUNK_SIZE = 25_000
INSERT_BATCH_SIZE = 5_000


def _normalise_column(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def _history_table(metadata: MetaData) -> Table:
    return Table(
        "contract_notices_hist",
        metadata,
        Column("row_hash", Text, primary_key=True),
        Column("source_file", Text, nullable=False),
        Column("contract_id", Text),
        Column("payload", JSON, nullable=False),
        schema="raw",
    )


def load_csv_dump(path: str, database_url: str | None = None) -> int:
    """Normalise and idempotently append one historical CSV dump.

    Historical snapshots use several header variants. The original row is retained
    as JSON after snake-case normalisation, while a stable hash prevents the same
    source row being loaded twice.
    """
    source_path = Path(path)
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    engine = create_engine(database_url or get_settings().database_url, pool_pre_ping=True)
    metadata = MetaData()
    history = _history_table(metadata)
    inserted = 0

    with engine.begin() as connection:
        connection.exec_driver_sql("create schema if not exists raw")
        history.create(connection, checkfirst=True)

        chunks = pd.read_csv(
            source_path,
            dtype=str,
            keep_default_na=False,
            encoding_errors="replace",
            on_bad_lines="warn",
            chunksize=CSV_CHUNK_SIZE,
        )
        for chunk in chunks:
            chunk.columns = [_normalise_column(column) for column in chunk.columns]
            rows: list[dict] = []
            for payload in chunk.to_dict(orient="records"):
                canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                row_hash = hashlib.sha256(
                    f"{source_path.name}:{canonical}".encode("utf-8")
                ).hexdigest()
                contract_id = payload.get("contract_id") or payload.get("cn_id")
                rows.append(
                    {
                        "row_hash": row_hash,
                        "source_file": source_path.name,
                        "contract_id": contract_id or None,
                        "payload": payload,
                    }
                )

            for offset in range(0, len(rows), INSERT_BATCH_SIZE):
                statement = insert(history).values(rows[offset : offset + INSERT_BATCH_SIZE])
                statement = statement.on_conflict_do_nothing(index_elements=["row_hash"])
                result = connection.execute(statement)
                inserted += max(result.rowcount or 0, 0)

    engine.dispose()
    logger.info("landed %s new historical rows from %s", inserted, source_path)
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="historical data.gov.au CSV file(s)")
    args = parser.parse_args()
    inserted = sum(load_csv_dump(path) for path in args.paths)
    logger.info("historical ingestion complete: %s newly inserted rows", inserted)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
