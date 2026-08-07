"""Compose a one-page bid/no-bid brief for a selected tender.

Sections: tender summary, agency spend history, incumbent/competitor
suppliers, fit score + rationale, amendment-risk note, recommended action.

Output is ALWAYS marked: "DRAFT - analyst review required" (human-in-the-loop).
"""
from __future__ import annotations

DRAFT_BANNER = "DRAFT - analyst review required"


def compose_brief(tender_id: str) -> str:
    # TODO(week-4): orchestrate sql_tool + rag_tool + ml_tool -> markdown brief
    raise NotImplementedError
