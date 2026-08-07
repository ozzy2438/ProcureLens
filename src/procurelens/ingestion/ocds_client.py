"""AusTender OCDS API client.

Fetches contract notices in OCDS schema and lands them as raw JSON rows in
Postgres (schema: raw.contract_notices). API docs:
https://github.com/austender/austender-ocds-api
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.tenders.gov.au/ocds"


def fetch_contract_notices(start: date, end: date) -> list[dict]:
    """Fetch contract notices published between start and end (paginated)."""
    releases: list[dict] = []
    url: str | None = (
        f"{BASE_URL}/findByDates/contractPublished/"
        f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z"
    )
    with httpx.Client(timeout=60) as client:
        while url:
            resp = client.get(url)
            resp.raise_for_status()
            payload = resp.json()
            releases.extend(payload.get("releases", []))
            url = payload.get("links", {}).get("next")
            logger.info("fetched %s releases so far", len(releases))
    return releases


def land_raw(releases: list[dict]) -> int:
    """Insert raw OCDS releases into raw.contract_notices (idempotent on ocid)."""
    # TODO(week-1): SQLAlchemy upsert into raw.contract_notices
    raise NotImplementedError


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--last-days", type=int, default=None)
    args = parser.parse_args()

    if args.last_days:
        end = datetime.utcnow().date()
        start = end - timedelta(days=args.last_days)
    else:
        start, end = args.start, args.end

    releases = fetch_contract_notices(start, end)
    logger.info("fetched %s releases total", len(releases))
    land_raw(releases)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
