"""Deterministic retrieval over versioned CPR and ANAO source summaries."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from procurelens.agent.guardrails import guard_text
from procurelens.config import get_settings

COLLECTION = "procurement_governance"


@dataclass(frozen=True)
class Citation:
    document: str
    page: int
    url: str
    section: str

    @property
    def label(self) -> str:
        return f"{self.document}, p. {self.page}"


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    content: str
    score: float
    citation: Citation

    def model_dump(self) -> dict[str, Any]:
        return {
            "id": self.chunk_id,
            "content": self.content,
            "score": self.score,
            "document": self.citation.document,
            "page": self.citation.page,
            "url": self.citation.url,
            "section": self.citation.section,
        }


@dataclass(frozen=True)
class RAGAnswer:
    answer: str
    sources: list[Citation]
    chunks: list[RetrievedChunk]

    def model_dump(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "sources": [asdict(source) for source in self.sources],
            "chunks": [chunk.model_dump() for chunk in self.chunks],
        }


class ProcurementRAGTool:
    """In-process retrieval with authoritative page-level citation metadata."""

    def __init__(self, corpus_path: str | Path) -> None:
        path = Path(corpus_path)
        raw_chunks = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw_chunks, list) or not raw_chunks:
            raise ValueError("RAG corpus must be a non-empty JSON list")
        self._chunks: list[dict[str, Any]] = []
        documents: list[str] = []
        for raw in raw_chunks:
            required = {"id", "document", "page", "url", "section", "content", "tags"}
            if not isinstance(raw, dict) or not required.issubset(raw):
                raise ValueError("every RAG chunk must contain source and page metadata")
            content = guard_text(str(raw["content"]), reject_injection=True).text
            chunk = {**raw, "content": content}
            self._chunks.append(chunk)
            documents.append(
                " ".join(
                    [
                        str(raw["section"]),
                        content,
                        " ".join(str(tag) for tag in raw["tags"]),
                    ]
                )
            )
        self._vectorizer = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), stop_words="english")
        self._matrix = self._vectorizer.fit_transform(documents)

    def retrieve(self, query: str, k: int = 6) -> list[RetrievedChunk]:
        if not 1 <= k <= 10:
            raise ValueError("k must be between 1 and 10")
        safe_query = guard_text(query, reject_injection=True).text
        query_vector = self._vectorizer.transform([safe_query])
        scores = np.asarray((self._matrix @ query_vector.T).toarray()).reshape(-1)
        ranked = sorted(
            enumerate(scores),
            key=lambda item: (-float(item[1]), str(self._chunks[item[0]]["id"])),
        )
        results: list[RetrievedChunk] = []
        for index, score in ranked:
            if score <= 0:
                continue
            raw = self._chunks[index]
            results.append(
                RetrievedChunk(
                    chunk_id=str(raw["id"]),
                    content=str(raw["content"]),
                    score=round(float(score), 6),
                    citation=Citation(
                        document=str(raw["document"]),
                        page=int(raw["page"]),
                        url=str(raw["url"]),
                        section=str(raw["section"]),
                    ),
                )
            )
            if len(results) == k:
                break
        return results

    def answer(self, query: str, k: int = 4) -> RAGAnswer:
        chunks = self.retrieve(query, k=k)
        if not chunks:
            return RAGAnswer(
                answer=(
                    "No sufficiently relevant passage was found in the curated CPR/ANAO corpus. "
                    "Do not infer a procurement rule without analyst verification."
                ),
                sources=[],
                chunks=[],
            )
        lines = [
            f"- {chunk.content} [{chunk.citation.label}]({chunk.citation.url})"
            for chunk in chunks
        ]
        answer = (
            "Retrieved procurement guidance (decision support only; not legal advice):\n"
            + "\n".join(lines)
        )
        return RAGAnswer(
            answer=answer,
            sources=[chunk.citation for chunk in chunks],
            chunks=chunks,
        )


def build_rag_tool(corpus_path: str | None = None) -> ProcurementRAGTool:
    return ProcurementRAGTool(corpus_path or get_settings().rag_corpus_path)


def retrieve(query: str, k: int = 6) -> list[dict[str, Any]]:
    """Backward-compatible retrieval facade."""
    return [chunk.model_dump() for chunk in build_rag_tool().retrieve(query, k)]
