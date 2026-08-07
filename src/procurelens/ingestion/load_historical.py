"""Bulk-load historical AusTender contract data (1999+) from data.gov.au CSVs.

Dataset: https://data.gov.au/data/dataset/historical-australian-government-contract-data
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def load_csv_dump(path: str) -> int:
    """Normalise one historical CSV dump and append to raw.contract_notices_hist."""
    # TODO(week-1): pandas read_csv with dtype map -> to_sql(raw.contract_notices_hist)
    raise NotImplementedError
