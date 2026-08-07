"""Natural language -> SQL over the dbt marts (read-only database role).

Safety rails: SELECT-only allowlist, statement timeout, row limit,
schema-scoped to marts.* only.
"""
from __future__ import annotations

ALLOWED_SCHEMAS = ("marts",)
MAX_ROWS = 500


def run_nl_query(question: str) -> dict:
    # TODO(week-4): schema-aware prompt -> SQL -> validate -> execute -> rows
    raise NotImplementedError
