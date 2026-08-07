"""RAG over the governance corpus (Commonwealth Procurement Rules, ANAO
procurement audit reports, selected agency annual reports).

Every answer chunk carries its source document + page for citation.
"""
from __future__ import annotations

COLLECTION = "procurement_governance"


def retrieve(query: str, k: int = 6) -> list[dict]:
    # TODO(week-4): chromadb / pgvector retrieval with metadata filters
    raise NotImplementedError
